package controllers

import (
	"net/http"

	"helmetdetection/models"
	"helmetdetection/services"
)

func Stream(w http.ResponseWriter, r *http.Request) {
	// Expect path /stream/{id}
	id := ""
	// trim prefix
	if len(r.URL.Path) > len("/stream/") {
		id = r.URL.Path[len("/stream/"):]
	}
	cam := models.FindByID(id)
	if cam == nil {
		http.NotFound(w, r)
		return
	}
	services.ServeMJPEGStream(w, cam.SourceType, cam.Source)
}
