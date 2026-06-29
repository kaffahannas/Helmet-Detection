document.addEventListener('DOMContentLoaded', function () {
    const streamImage = document.querySelector('.live-video');
    if (streamImage) {
        streamImage.addEventListener('error', function () {
            console.warn('Live stream error, coba refresh halaman.');
        });
    }
});
