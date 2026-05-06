document.addEventListener('DOMContentLoaded', () => {
    const statusBar = document.getElementById('taskProgress');
    
    if (statusBar) {
        let progress = 10;
        const interval = setInterval(() => {
            progress = Math.min(progress + Math.random() * 15, 90);
            statusBar.style.width = `${progress}%`;
            if (progress >= 90) clearInterval(interval);
        }, 2000);
    }
});
