package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

const (
	pythonURL  = "http://127.0.0.1:5000"
	videosDir  = "../bukti_pelanggaran"
	staticDir  = "./static"
	listenAddr = ":8081"
	nCams      = 3
)

// streamByID proxies /stream/{id} → Python /video_feed/{id} with MJPEG flushing.
func streamByID(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/stream/")
	if len(id) != 1 || id[0] < '0' || id[0] >= byte('0'+nCams) {
		http.NotFound(w, r)
		return
	}
	resp, err := http.Get(pythonURL + "/video_feed/" + id)
	if err != nil {
		http.Error(w, `{"error":"detector offline"}`, http.StatusServiceUnavailable)
		return
	}
	defer resp.Body.Close()

	for k, vv := range resp.Header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(resp.StatusCode)

	flusher, canFlush := w.(http.Flusher)
	buf := make([]byte, 4096)
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := w.Write(buf[:n]); werr != nil {
				return // client disconnected
			}
			if canFlush {
				flusher.Flush()
			}
		}
		if err != nil {
			return
		}
	}
}

// proxy forwards a request to a fixed Python URL and streams the response.
func proxy(target string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		resp, err := http.Get(target)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprint(w, `{"error":"detector offline"}`)
			return
		}
		defer resp.Body.Close()
		for k, vv := range resp.Header {
			for _, v := range vv {
				w.Header().Add(k, v)
			}
		}
		w.WriteHeader(resp.StatusCode)
		io.Copy(w, resp.Body)
	}
}

// proxyPath proxies requests like /api/stats/0 → Python /api/stats/0.
func proxyPath(prefix string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		suffix := strings.TrimPrefix(r.URL.Path, prefix)
		proxy(pythonURL + prefix + suffix)(w, r)
	}
}

// videoHandler serves .avi violation files with path-traversal protection.
func videoHandler(w http.ResponseWriter, r *http.Request) {
	name := filepath.Base(r.URL.Path)
	if !strings.HasSuffix(name, ".avi") {
		http.NotFound(w, r)
		return
	}
	full := filepath.Join(videosDir, name)
	if _, err := os.Stat(full); os.IsNotExist(err) {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, name))
	http.ServeFile(w, r, full)
}

// healthHandler reports Go + Python status.
func healthHandler(w http.ResponseWriter, r *http.Request) {
	result := map[string]interface{}{"go_server": "ok"}
	resp, err := http.Get(pythonURL + "/health")
	if err != nil {
		result["python_detector"] = "OFFLINE — is detector.py running?"
	} else {
		defer resp.Body.Close()
		var d interface{}
		json.NewDecoder(resp.Body).Decode(&d)
		result["python_detector"] = d
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func main() {
	mux := http.NewServeMux()

	// Dashboard (SPA — serves index.html for any unmatched route)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, filepath.Join(staticDir, "index.html"))
	})

	// Static assets (CSS, JS)
	mux.Handle("/static/",
		http.StripPrefix("/static/", http.FileServer(http.Dir(staticDir))))

	// Health
	mux.HandleFunc("/health", healthHandler)

	// MJPEG streams: /stream/0, /stream/1, /stream/2
	mux.HandleFunc("/stream/", streamByID)

	// JSON API
	mux.HandleFunc("/api/stats",      proxy(pythonURL+"/api/stats"))      // all cameras
	mux.HandleFunc("/api/stats/",     proxyPath("/api/stats/"))            // per camera
	mux.HandleFunc("/api/violations", proxy(pythonURL+"/api/violations"))

	// Violation video downloads
	mux.HandleFunc("/videos/", videoHandler)

	log.Printf("Dashboard  →  http://localhost%s\n", listenAddr)
	log.Printf("Detector   →  %s  (%d cameras)\n", pythonURL, nCams)
	log.Fatal(http.ListenAndServe(listenAddr, mux))
}
