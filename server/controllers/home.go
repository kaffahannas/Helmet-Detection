package controllers

import (
	"helmet-detection/server/config"
	"net/http"
	"path/filepath"
)

// HomeHandler serves the dashboard index.html for any unmatched route
func HomeHandler(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, filepath.Join(config.StaticDir, "index.html"))
}
