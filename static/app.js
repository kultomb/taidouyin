document.addEventListener('DOMContentLoaded', () => {
    const volumeSlider = document.getElementById('bgVolume');
    const volumeValue = document.getElementById('volumeValue');
    const form = document.getElementById('translateForm');
    const submitBtn = document.getElementById('submitBtn');
    const videoUrlInput = document.getElementById('videoUrl');
    const burnSubtitlesCheckbox = document.getElementById('burnSubtitles');
    const ttsProviderSelect = document.getElementById('ttsProvider');
    const ttsToggleBtns = document.querySelectorAll('.tts-toggle-btn');
    let selectedTtsProvider = 'edge';

    // TTS Toggle Buttons
    ttsToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            ttsToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedTtsProvider = btn.dataset.tts;
        });
    });

    const btnGetCookie = document.getElementById('btnGetCookie');

    const processingCard = document.getElementById('processingCard');
    const currentSubStep = document.getElementById('currentSubStep');
    const progressLineFill = document.getElementById('progressLineFill');
    const terminalBody = document.getElementById('terminalBody');

    const resultsCard = document.getElementById('resultsCard');
    const originalVideoPlayer = document.getElementById('originalVideoPlayer');
    const translatedVideoPlayer = document.getElementById('translatedVideoPlayer');
    const downloadVideoBtn = document.getElementById('downloadVideoBtn');
    const downloadSrtBtn = document.getElementById('downloadSrtBtn');
    const downloadAudioBtn = document.getElementById('downloadAudioBtn');

    let pollInterval = null;
    let displayedLogCount = 0;

    // Handle range slider updates
    volumeSlider.addEventListener('input', (e) => {
        const val = Math.round(e.target.value * 100);
        volumeValue.textContent = `${val}%`;
    });

    // Handle Douyin cookie login button
    btnGetCookie.addEventListener('click', async () => {
        btnGetCookie.disabled = true;
        const spanText = btnGetCookie.querySelector('span');
        const originalText = spanText.textContent;
        spanText.textContent = 'Đang xác thực...';

        processingCard.classList.remove('hidden');
        appendLogLine('Đang gửi yêu cầu mở trình duyệt đăng nhập Douyin...', 'info');

        try {
            const response = await fetch('/api/get-cookies', {
                method: 'POST'
            });
            const data = await response.json();
            if (data.status === 'success') {
                appendLogLine(`[ĐĂNG NHẬP] ${data.message}`, 'success');
                alert(`Đăng nhập Douyin thành công!\n${data.message}`);
            } else {
                appendLogLine(`[ĐĂNG NHẬP THẤT BẠI] ${data.message}`, 'error');
                alert(`Không thể lấy cookie: ${data.message}`);
            }
        } catch (err) {
            appendLogLine(`[ĐĂNG NHẬP LỖI] Lỗi kết nối server: ${err.message}`, 'error');
            alert(`Lỗi kết nối tới máy chủ khi yêu cầu lấy cookie.`);
        } finally {
            btnGetCookie.disabled = false;
            spanText.textContent = originalText;
        }
    });

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const url = videoUrlInput.value.trim();
        if (!url) return;

        const bgVolume = parseFloat(volumeSlider.value);
        const burnSubtitles = burnSubtitlesCheckbox.checked;
        const ttsProvider = selectedTtsProvider;

        // Reset UI States
        submitBtn.disabled = true;
        submitBtn.querySelector('span').textContent = 'Đang xử lý...';
        processingCard.classList.remove('hidden');
        resultsCard.classList.add('hidden');

        // Reset steps nodes
        document.querySelectorAll('.step-node').forEach(node => {
            node.classList.remove('active', 'completed');
        });
        progressLineFill.style.width = '0%';

        // Reset Terminal Logs
        terminalBody.innerHTML = '';
        appendLogLine('Sản phẩm khởi động. Đang gửi yêu cầu dịch thuật tới máy chủ...', 'info');
        displayedLogCount = 0;

        try {
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, bg_volume: bgVolume, burn_subtitles: burnSubtitles, tts_provider: ttsProvider })
            });

            if (!response.ok) {
                throw new Error('Lỗi phản hồi từ máy chủ.');
            }

            const data = await response.json();
            const jobId = data.job_id;

            appendLogLine(`Đã tạo tiến trình xử lý với mã: ${jobId}`, 'success');

            // Start polling status
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => pollJobStatus(jobId), 1200);

        } catch (err) {
            appendLogLine(`Lỗi khởi động tiến trình: ${err.message}`, 'error');
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = 'Bắt đầu tiến trình xử lý';
        }
    });

    // Polling function
    async function pollJobStatus(jobId) {
        try {
            const response = await fetch(`/api/status/${jobId}`);
            if (!response.ok) {
                throw new Error('Không thể lấy thông tin trạng thái.');
            }

            const data = await response.json();

            // 1. Update Logs in Terminal
            const logs = data.logs || [];
            if (logs.length > displayedLogCount) {
                for (let i = displayedLogCount; i < logs.length; i++) {
                    const line = logs[i];
                    let type = 'info';
                    if (line.includes('LỖI') || line.includes('ERROR') || line.includes('failed')) {
                        type = 'error';
                    } else if (line.includes('thành công') || line.includes('success') || line.includes('completed')) {
                        type = 'success';
                    }
                    appendLogLine(line, type);
                }
                displayedLogCount = logs.length;
            }

            // 2. Update Sub-step Description
            currentSubStep.textContent = data.sub_step || 'Đang thực hiện...';

            // 3. Update Visual Steps Progress Bar (1 to 8)
            const currentStep = data.step || 0;
            updateStepProgressUI(currentStep);

            // 4. Handle Completion/Failure
            if (data.status === 'completed') {
                clearInterval(pollInterval);
                appendLogLine('--- TIẾN TRÌNH HOÀN THÀNH XUẤT SẮC ---', 'success');

                // Show final step 8 as completed
                updateStepProgressUI(8, true);

                // Show Results Card
                resultsCard.classList.remove('hidden');

                // Set video players sources
                originalVideoPlayer.src = data.result.original_video_url;
                translatedVideoPlayer.src = data.result.translated_video_url;

                // Set download buttons links
                downloadVideoBtn.href = data.result.translated_video_url;
                downloadSrtBtn.href = data.result.srt_url;
                downloadAudioBtn.href = data.result.audio_url;

                // Reset submit button
                submitBtn.disabled = false;
                submitBtn.querySelector('span').textContent = 'Bắt đầu tiến trình xử lý';

                // Smooth scroll to results
                setTimeout(() => {
                    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 300);

            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                appendLogLine(`Lỗi hệ thống: ${data.error || 'Tiến trình kết thúc không mong muốn.'}`, 'error');

                // Reset submit button
                submitBtn.disabled = false;
                submitBtn.querySelector('span').textContent = 'Bắt đầu tiến trình xử lý';
            }

        } catch (err) {
            appendLogLine(`Lỗi trong quá trình theo dõi tiến độ: ${err.message}`, 'error');
        }
    }

    // Update Progress Step Nodes
    function updateStepProgressUI(step, isFinished = false) {
        // step is from 1 to 8. If step is 0 (initial/idle) do nothing.
        if (step < 1) return;

        // Update fill line percentage
        // Step 1: 0% | Step 2: 14.3% | Step 8: 100%
        let fillPercent = 0;
        if (step > 1) {
            fillPercent = Math.min(((step - 1) / 7) * 100, 100);
        }
        if (isFinished) {
            fillPercent = 100;
        }
        progressLineFill.style.width = `${fillPercent}%`;

        // Update each step circle
        const stepNodes = document.querySelectorAll('.step-node');
        stepNodes.forEach(node => {
            const nodeStep = parseInt(node.getAttribute('data-step'));

            node.classList.remove('active', 'completed');

            if (isFinished) {
                node.classList.add('completed');
            } else {
                if (nodeStep < step) {
                    node.classList.add('completed');
                } else if (nodeStep === step) {
                    node.classList.add('active');
                }
            }
        });
    }

    // Log printer helper
    function appendLogLine(message, type = 'info') {
        const div = document.createElement('div');
        div.className = `log-line ${type}`;
        div.textContent = message;
        terminalBody.appendChild(div);

        // Scroll terminal to the bottom
        terminalBody.scrollTop = terminalBody.scrollHeight;
    }
});
