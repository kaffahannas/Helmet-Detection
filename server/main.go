package main

import (
	"helmet-detection/server/config"
	"helmet-detection/server/routes"
	"log"
	"net/http"
)

func main() {
	router := routes.NewRouter()

	log.Printf("Dashboard  →  http://localhost%s\n", config.ListenAddr)
	log.Printf("Detector   →  %s  (%d cameras)\n", config.PythonURL, config.NCams)
	log.Fatal(http.ListenAndServe(config.ListenAddr, router))
}
