package controllers

import (
	"helmet-detection/server/config"
	"net/http"
	"strings"
)

// StreamByID proxies /stream/{id} → Python /video_feed/{id} with MJPEG flushing.
func StreamByID(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/stream/")
	if len(id) != 1 || id[0] < '0' || id[0] >= byte('0'+config.NCams) {
		http.NotFound(w, r)
		return
	}
	resp, err := http.Get(config.PythonURL + "/video_feed/" + id)
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
