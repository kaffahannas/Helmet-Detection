package services

import (
	"io"
	"log"
	"net/http"
	"os/exec"
	"runtime"
)

// ServeMJPEGStream memulai ffmpeg untuk mengubah berbagai sumber video ke MJPEG dan mengirimkannya ke browser.
func ServeMJPEGStream(w http.ResponseWriter, sourceType, source string) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming tidak didukung oleh browser", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "multipart/x-mixed-replace; boundary=ffmpeg")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "close")

	var args []string
	switch sourceType {
	case "rtsp":
		args = []string{"-rtsp_transport", "tcp", "-i", source, "-f", "mjpeg", "-q:v", "5", "-"}
	case "file":
		// -re to read input in real time
		args = []string{"-re", "-i", source, "-f", "mjpeg", "-q:v", "5", "-"}
	case "dshow":
		// Windows DirectShow. source is device name.
		if runtime.GOOS == "windows" {
			args = []string{"-f", "dshow", "-i", "video=" + source, "-f", "mjpeg", "-q:v", "5", "-"}
		} else {
			// fallback to trying v4l2 on linux with device path in source
			args = []string{"-f", "v4l2", "-i", source, "-f", "mjpeg", "-q:v", "5", "-"}
		}
	default:
		http.Error(w, "Tipe sumber tidak didukung", http.StatusBadRequest)
		return
	}

	cmd := exec.Command("ffmpeg", args...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		http.Error(w, "Gagal memulai stream: "+err.Error(), http.StatusInternalServerError)
		return
	}

	cmd.Stderr = log.Writer()
	if err := cmd.Start(); err != nil {
		http.Error(w, "Gagal menjalankan ffmpeg: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer func() {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
	}()

	buffer := make([]byte, 4096)
	for {
		n, readErr := stdout.Read(buffer)
		if n > 0 {
			if _, writeErr := w.Write(buffer[:n]); writeErr != nil {
				break
			}
			flusher.Flush()
		}
		if readErr != nil {
			if readErr != io.EOF {
				log.Printf("FFmpeg read error: %v", readErr)
			}
			break
		}
	}

	_ = cmd.Wait()
}
