package controllers

import (
	"fmt"
	"helmet-detection/server/config"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// VideoHandler serves .avi violation files with path-traversal protection.
func VideoHandler(w http.ResponseWriter, r *http.Request) {
	name := filepath.Base(r.URL.Path)
	if !strings.HasSuffix(name, ".avi") {
		http.NotFound(w, r)
		return
	}
	full := filepath.Join(config.VideosDir, name)
	if _, err := os.Stat(full); os.IsNotExist(err) {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, name))
	http.ServeFile(w, r, full)
}
