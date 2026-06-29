package controllers

import (
	"html/template"
	"net/http"
	"path/filepath"

	"helmetdetection/models"
)

func Index(w http.ResponseWriter, r *http.Request) {
	cameras := models.Cameras

	data := map[string]any{
		"Title":   "Helmet Detection CCTV Live",
		"Cameras": cameras,
		"Site": map[string]string{
			"Name": "Helmet Detection",
		},
	}

	renderTemplate(w, "index.html", data)
}

func renderTemplate(w http.ResponseWriter, templateName string, data any) {
	path := filepath.Join("templates", templateName)
	tmpl, err := template.ParseFiles(path)
	if err != nil {
		http.Error(w, "Gagal memuat halaman: "+err.Error(), http.StatusInternalServerError)
		return
	}

	if err := tmpl.Execute(w, data); err != nil {
		http.Error(w, "Gagal merender halaman: "+err.Error(), http.StatusInternalServerError)
	}
}
