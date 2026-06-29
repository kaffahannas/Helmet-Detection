package controllers

import (
	"fmt"
	"helmet-detection/server/config"
	"io"
	"net/http"
	"strings"
)

// Proxy forwards a request to a fixed Python URL and streams the response.
func Proxy(target string) http.HandlerFunc {
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

// ProxyPath proxies requests like /api/stats/0 → Python /api/stats/0.
func ProxyPath(prefix string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		suffix := strings.TrimPrefix(r.URL.Path, prefix)
		Proxy(config.PythonURL + prefix + suffix)(w, r)
	}
}
