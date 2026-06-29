package routes

import (
	"helmet-detection/server/config"
	"helmet-detection/server/controllers"
	"net/http"
)

func NewRouter() http.Handler {
	mux := http.NewServeMux()

	// Dashboard (SPA — serves index.html for any unmatched route)
	mux.HandleFunc("/", controllers.HomeHandler)

	// Static assets (CSS, JS)
	mux.Handle("/static/",
		http.StripPrefix("/static/", http.FileServer(http.Dir(config.StaticDir))))

	// Health
	mux.HandleFunc("/health", controllers.HealthHandler)

	// MJPEG streams: /stream/0, /stream/1, /stream/2
	mux.HandleFunc("/stream/", controllers.StreamByID)

	// JSON API
	mux.HandleFunc("/api/stats", controllers.Proxy(config.PythonURL+"/api/stats"))      // all cameras
	mux.HandleFunc("/api/stats/", controllers.ProxyPath("/api/stats/"))                 // per camera
	mux.HandleFunc("/api/violations", controllers.Proxy(config.PythonURL+"/api/violations"))

	// Violation video downloads
	mux.HandleFunc("/videos/", controllers.VideoHandler)

	return mux
}
