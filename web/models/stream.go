package models

// Camera menyimpan konfigurasi sumber video yang dapat ditayangkan.
type Camera struct {
	ID          string
	Name        string
	Description string
	SourceType  string // "rtsp", "file", "dshow"
	Source      string // RTSP URL, file path, or device name
	StreamPath  string // e.g. "/stream/{id}"
	Location    string
	Region      string
}

// Cameras berisi daftar sumber yang tersedia untuk tampilan testing.
var Cameras = []Camera{
	{
		ID:          "test1",
		Name:        "Test Video 1",
		Description: "File video lokal test1.mp4",
		SourceType:  "file",
		Source:      "../test1.mp4",
		StreamPath:  "/stream/test1",
		Location:    "Local",
		Region:      "Test",
	},
	{
		ID:          "test2",
		Name:        "Test Video 2",
		Description: "File video lokal test2.mp4",
		SourceType:  "file",
		Source:      "../test2.mp4",
		StreamPath:  "/stream/test2",
		Location:    "Local",
		Region:      "Test",
	},
	{
		ID:          "webcam",
		Name:        "Webcam",
		Description: "Local webcam (placeholder device name)",
		SourceType:  "dshow",
		Source:      "Integrated Camera",
		StreamPath:  "/stream/webcam",
		Location:    "Local",
		Region:      "Webcam",
	},
}

// FindByID mengembalikan pointer ke Camera sesuai ID, atau nil bila tidak ditemukan.
func FindByID(id string) *Camera {
	for i := range Cameras {
		if Cameras[i].ID == id {
			return &Cameras[i]
		}
	}
	return nil
}
