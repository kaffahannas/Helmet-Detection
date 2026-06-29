package controllers

import (
	"encoding/json"
	"helmet-detection/server/config"
	"net/http"
)

// HealthHandler reports Go + Python status.
func HealthHandler(w http.ResponseWriter, r *http.Request) {
	result := map[string]interface{}{"go_server": "ok"}
	resp, err := http.Get(config.PythonURL + "/health")
	if err != nil {
		result["python_detector"] = "OFFLINE — is detector.py running?"
	} else {
		defer resp.Body.Close()
		var d interface{}
		json.NewDecoder(resp.Body).Decode(&d)
		result["python_detector"] = d
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}
