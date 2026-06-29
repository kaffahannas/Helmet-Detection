package routes

import (
	"net/http"

	"helmetdetection/controllers"
)

func NewRouter() http.Handler {
	mux := http.NewServeMux()

	mux.Handle("/static/", http.StripPrefix("/static/", http.FileServer(http.Dir("static"))))
	mux.HandleFunc("/", controllers.Index)
	// stream endpoint expects paths like /stream/{id}
	mux.HandleFunc("/stream/", controllers.Stream)

	return mux
}
