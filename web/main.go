package main

import (
	"log"
	"net/http"
	"time"

	"helmetdetection/routes"
)

func main() {
	router := routes.NewRouter()

	server := &http.Server{
		Addr:         ":8081",
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 0,
		IdleTimeout:  30 * time.Second,
	}

	log.Println("Starting Helmet Detection web server on http://localhost:8081")
	if err := server.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
