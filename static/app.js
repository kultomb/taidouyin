document.addEventListener('DOMContentLoaded', () => {
    const volumeSlider = document.getElementById('bgVolume');
    const volumeValue = document.getElementById('volumeValue');
    const form = document.getElementById('translateForm');
    const submitBtn = document.getElementById('submitBtn');
    const videoUrlInput = document.getElementById('videoUrl');
    const burnSubtitlesCheckbox = document.getElementById('burnSubtitles');
    const ttsOptionCards = document.querySelectorAll('.tts-option-card');
    const asrToggleBtns = document.querySelectorAll('.asr-toggle-btn');
    const translateToggleBtns = document.querySelectorAll('.translate-toggle-btn');
    const processToggleBtns = document.querySelectorAll('.process-toggle-btn');
    let selectedTtsProvider = 'edge';
    let selectedAsrMode = 'audio';
    let selectedTranslateProvider = 'gemini';
    let selectedProcessMode = 'ocr';

    const voices = {
        edge: [
            { value: "", label: "🎭 Tự động phân vai (Đa giọng Nam/Nữ)" },
            { value: "vi-VN-HoaiMyNeural", label: "🔊 Nữ miền Nam (Hoài My)" },
            { value: "vi-VN-NamMinhNeural", label: "🔊 Nam miền Nam (Nam Minh)" }
        ],
        google: [
            { value: "", label: "🎭 Tự động phân vai (Đa giọng Nam/Nữ)" },
            // Neural2 voices
            { value: "vi-VN-Neural2-A", label: "🎙️ Neural2 A - Nữ HN" },
            { value: "vi-VN-Neural2-D", label: "🎙️ Neural2 D - Nam SG" },
            // Wavenet voices
            { value: "vi-VN-Wavenet-A", label: "📻 Wavenet A - Nữ HN" },
            { value: "vi-VN-Wavenet-B", label: "📻 Wavenet B - Nam HN" },
            { value: "vi-VN-Wavenet-C", label: "📻 Wavenet C - Nữ SG" },
            { value: "vi-VN-Wavenet-D", label: "📻 Wavenet D - Nam SG" },
            // Standard voices
            { value: "vi-VN-Standard-A", label: "📢 Standard A - Nữ HN" },
            { value: "vi-VN-Standard-B", label: "📢 Standard B - Nam HN" },
            { value: "vi-VN-Standard-C", label: "📢 Standard C - Nữ SG" },
            { value: "vi-VN-Standard-D", label: "📢 Standard D - Nam SG" }
        ],
        gemini: [
            { value: "", label: "🎭 Tự động phân vai (Đa giọng 30 giọng AI)" },
            // --- Nữ (Female) - 14 giọng theo danh sách chính thức ---
            { value: "Zephyr", label: "🌟 Zephyr - Nữ (Tươi sáng, trong trẻo)" },
            { value: "Achernar", label: "🌟 Achernar - Nữ (Nhẹ nhàng, mềm mại)" },
            { value: "Aoede", label: "🌟 Aoede - Nữ (Nhẹ nhàng, phóng khoáng)" },
            { value: "Autonoe", label: "🌟 Autonoe - Nữ (Tươi sáng, rạng rỡ)" },
            { value: "Despina", label: "🌟 Despina - Nữ (Mượt mà, uyển chuyển)" },
            { value: "Callirrhoe", label: "🌟 Callirrhoe - Nữ (Thoải mái, tự nhiên)" },
            { value: "Erinome", label: "🌟 Erinome - Nữ (Rõ ràng, rành mạch)" },
            { value: "Gacrux", label: "🌟 Gacrux - Nữ (Chín chắn, trưởng thành)" },
            { value: "Kore", label: "🌟 Kore - Nữ (Vững vàng, quyết đoán)" },
            { value: "Leda", label: "🌟 Leda - Nữ (Trẻ trung, năng động)" },
            { value: "Laomedeia", label: "🌟 Laomedeia - Nữ (Vui tươi, sôi nổi)" },
            { value: "Pulcherrima", label: "🌟 Pulcherrima - Nữ (Rõ ràng, hướng ngoại)" },
            { value: "Sulafat", label: "🌟 Sulafat - Nữ (Ấm áp, truyền cảm)" },
            { value: "Vindemiatrix", label: "🌟 Vindemiatrix - Nữ (Dịu dàng, từ tốn)" },
            // --- Nam (Male) - 16 giọng theo danh sách chính thức ---
            { value: "Charon", label: "🌟 Charon - Nam (Nghiêm túc, cung cấp thông tin)" },
            { value: "Enceladus", label: "🌟 Enceladus - Nam (Kiểu giọng hơi, truyền cảm)" },
            { value: "Fenrir", label: "🌟 Fenrir - Nam (Sôi nổi, dễ kích động)" },
            { value: "Puck", label: "🌟 Puck - Nam (Vui vẻ, năng động)" },
            { value: "Achird", label: "🌟 Achird - Nam (Thân thiện, gần gũi)" },
            { value: "Algenib", label: "🌟 Algenib - Nam (Khàn nhẹ, có độ gai)" },
            { value: "Algieba", label: "🌟 Algieba - Nam (Mượt mà, trầm ấm)" },
            { value: "Alnilam", label: "🌟 Alnilam - Nam (Vững vàng, dứt khoát)" },
            { value: "Orus", label: "🌟 Orus - Nam (Vững chãi, quyền lực)" },
            { value: "Iapetus", label: "🌟 Iapetus - Nam (Rõ ràng, dễ nghe)" },
            { value: "Rasalgethi", label: "🌟 Rasalgethi - Nam (Trực quan, hướng dẫn)" },
            { value: "Schedar", label: "🌟 Schedar - Nam (Điềm đạm, đều đặn)" },
            { value: "Sadachbia", label: "🌟 Sadachbia - Nam (Sinh động, đầy sức sống)" },
            { value: "Sadaltager", label: "🌟 Sadaltager - Nam (Thông thái, hiểu biết)" },
            { value: "Umbriel", label: "🌟 Umbriel - Nam (Thư thái, dễ chịu)" },
            { value: "Zubenelgenubi", label: "🌟 Zubenelgenubi - Nam (Tự nhiên, bình dị)" }
        ]
    };

    // --- Gender-specific voice lists (cho dropdown Nữ / Nam riêng) ---
    function splitByGender(list) {
        const female = [{ value: "", label: "Tự động" }];
        const male = [{ value: "", label: "Tự động" }];
        list.forEach(v => {
            if (!v.value) return; // skip "auto" line
            const lbl = (v.label || "").toLowerCase();
            if (lbl.includes("nữ") || lbl.includes("female")) {
                female.push(v);
            } else if (lbl.includes("nam") || lbl.includes("male")) {
                male.push(v);
            }
        });
        return { female, male };
    }

    const genderVoices = {
        edge: splitByGender(voices.edge),
        google: splitByGender(voices.google),
        gemini: splitByGender(voices.gemini)
    };

    let selectedEdgeVoice = '';
    let selectedGoogleVoice = '';
    let selectedGeminiVoice = '';
    let selectedEdgeFemale = '', selectedEdgeMale = '';
    let selectedGoogleFemale = '', selectedGoogleMale = '';
    let selectedGeminiFemale = '', selectedGeminiMale = '';

    // --- Main voice dropdown refs ---
    const edgeSelect = document.getElementById('edgeVoiceSelect');
    const edgeTrigger = document.getElementById('edgeVoiceTrigger');
    const edgeOptionsContainer = document.getElementById('edgeVoiceOptions');
    const edgeSelectedText = document.getElementById('edgeVoiceSelectedText');

    const googleSelect = document.getElementById('googleVoiceSelect');
    const googleTrigger = document.getElementById('googleVoiceTrigger');
    const googleOptionsContainer = document.getElementById('googleVoiceOptions');
    const googleSelectedText = document.getElementById('googleVoiceSelectedText');

    const geminiSelect = document.getElementById('geminiVoiceSelect');
    const geminiTrigger = document.getElementById('geminiVoiceTrigger');
    const geminiOptionsContainer = document.getElementById('geminiVoiceOptions');
    const geminiSelectedText = document.getElementById('geminiVoiceSelectedText');

    // --- Gender voice dropdown refs ---
    const edgeGenderRow = document.getElementById('edgeGenderVoices');
    const googleGenderRow = document.getElementById('googleGenderVoices');
    const geminiGenderRow = document.getElementById('geminiGenderVoices');

    function populateCustomSelect(container, triggerText, selectEl, optionsList, getVal, setVal, onChange) {
        if (!container) return;
        container.innerHTML = '';
        optionsList.forEach(v => {
            const opt = document.createElement('div');
            opt.classList.add('custom-option');
            if (v.value === getVal()) {
                opt.classList.add('selected');
                triggerText.textContent = v.label;
            }
            opt.dataset.value = v.value;
            opt.textContent = v.label;

            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                setVal(v.value);
                triggerText.textContent = v.label;

                container.querySelectorAll('.custom-option').forEach(c => {
                    c.classList.remove('selected');
                });
                opt.classList.add('selected');
                selectEl.classList.remove('active');
                if (onChange) onChange(v.value);
            });
            container.appendChild(opt);
        });
    }

    function toggleGenderRow(provider, voiceValue) {
        const row = provider === 'edge' ? edgeGenderRow : (provider === 'google' ? googleGenderRow : geminiGenderRow);
        if (!row) return;
        row.style.display = (voiceValue === '') ? 'flex' : 'none';
    }

    populateCustomSelect(
        edgeOptionsContainer, edgeSelectedText, edgeSelect,
        voices.edge,
        () => selectedEdgeVoice,
        (val) => { selectedEdgeVoice = val; toggleGenderRow('edge', val); }
    );

    populateCustomSelect(
        googleOptionsContainer, googleSelectedText, googleSelect,
        voices.google,
        () => selectedGoogleVoice,
        (val) => { selectedGoogleVoice = val; toggleGenderRow('google', val); }
    );

    populateCustomSelect(
        geminiOptionsContainer, geminiSelectedText, geminiSelect,
        voices.gemini,
        () => selectedGeminiVoice,
        (val) => { selectedGeminiVoice = val; toggleGenderRow('gemini', val); }
    );

    // Hiển thị dropdown Nữ/Nam ngay khi load trang (mặc định "Tự động phân vai")
    toggleGenderRow('edge', selectedEdgeVoice);
    toggleGenderRow('google', selectedGoogleVoice);
    toggleGenderRow('gemini', selectedGeminiVoice);

    // Populate gender dropdowns
    function setupGenderDropdown(provider, gender) {
        const cap = gender.charAt(0).toUpperCase() + gender.slice(1);
        const container = document.getElementById(`${provider}${cap}Options`);
        const trigger = document.getElementById(`${provider}${cap}Trigger`);
        const selectEl = document.getElementById(`${provider}${cap}Select`);
        const selectedText = document.getElementById(`${provider}${cap}SelectedText`);

        const getter = () => {
            if (provider === 'edge') {
                return gender === 'female' ? selectedEdgeFemale : selectedEdgeMale;
            } else if (provider === 'gemini') {
                return gender === 'female' ? selectedGeminiFemale : selectedGeminiMale;
            } else {
                return gender === 'female' ? selectedGoogleFemale : selectedGoogleMale;
            }
        };
        const setter = (val) => {
            if (provider === 'edge') {
                if (gender === 'female') selectedEdgeFemale = val; else selectedEdgeMale = val;
            } else if (provider === 'gemini') {
                if (gender === 'female') selectedGeminiFemale = val; else selectedGeminiMale = val;
            } else {
                if (gender === 'female') selectedGoogleFemale = val; else selectedGoogleMale = val;
            }
        };

        populateCustomSelect(container, selectedText, selectEl, genderVoices[provider][gender], getter, setter);

        if (trigger && selectEl) {
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                selectEl.classList.toggle('active');
            });
        }
        return selectEl;
    }

    const genderSelects = [
        setupGenderDropdown('edge', 'female'),
        setupGenderDropdown('edge', 'male'),
        setupGenderDropdown('google', 'female'),
        setupGenderDropdown('google', 'male'),
        setupGenderDropdown('gemini', 'female'),
        setupGenderDropdown('gemini', 'male')
    ];

    if (edgeTrigger && edgeSelect) {
        edgeTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (googleSelect) googleSelect.classList.remove('active');
            genderSelects.forEach(s => s && s.classList.remove('active'));
            edgeSelect.classList.toggle('active');
        });
    }

    if (googleTrigger && googleSelect) {
        googleTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (edgeSelect) edgeSelect.classList.remove('active');
            if (geminiSelect) geminiSelect.classList.remove('active');
            genderSelects.forEach(s => s && s.classList.remove('active'));
            googleSelect.classList.toggle('active');
        });
    }

    if (geminiTrigger && geminiSelect) {
        geminiTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (edgeSelect) edgeSelect.classList.remove('active');
            if (googleSelect) googleSelect.classList.remove('active');
            genderSelects.forEach(s => s && s.classList.remove('active'));
            geminiSelect.classList.toggle('active');
        });
    }

    document.addEventListener('click', () => {
        if (edgeSelect) edgeSelect.classList.remove('active');
        if (googleSelect) googleSelect.classList.remove('active');
        if (geminiSelect) geminiSelect.classList.remove('active');
        genderSelects.forEach(s => s && s.classList.remove('active'));
    });

    ttsOptionCards.forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.custom-select')) {
                return;
            }
            ttsOptionCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            selectedTtsProvider = card.dataset.tts;
        });
    });

    // ASR Toggle Buttons
    asrToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            asrToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedAsrMode = btn.dataset.asr;
        });
    });

    // Translate Toggle Buttons
    translateToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            translateToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedTranslateProvider = btn.dataset.translate;
        });
    });

    // Process Toggle Buttons
    processToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            processToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedProcessMode = btn.dataset.process;
        });
    });

    const styleToggleBtns = document.querySelectorAll('.style-toggle-btn');
    let selectedTranslateStyle = 'default';

    // Style Toggle Buttons
    styleToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            styleToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedTranslateStyle = btn.dataset.style;
        });
    });

    const btnGetCookie = document.getElementById('btnGetCookie');

    const processingCard = document.getElementById('processingCard');
    const currentSubStep = document.getElementById('currentSubStep');
    const progressLineFill = document.getElementById('progressLineFill');
    const terminalBody = document.getElementById('terminalBody');

    const ocrSelectionCard = document.getElementById('ocrSelectionCard');
    const ocrVideoPlayer = document.getElementById('ocrVideoPlayer');
    const btnStartOcr = document.getElementById('btnStartOcr');
    const btnSkipOcr = document.getElementById('btnSkipOcr');
    let currentJobId = null;

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

    const ttsSpeedSlider = document.getElementById('ttsSpeed');
    const speedValue = document.getElementById('speedValue');
    if (ttsSpeedSlider) {
        ttsSpeedSlider.addEventListener('input', (e) => {
            speedValue.textContent = parseFloat(e.target.value).toFixed(2) + 'x';
        });
    }

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
        const asrMode = selectedAsrMode;
        const translateProvider = selectedTranslateProvider;
        const processMode = selectedProcessMode;
        const voiceName = (selectedTtsProvider === 'edge') ? selectedEdgeVoice : (selectedTtsProvider === 'gemini' ? selectedGeminiVoice : selectedGoogleVoice);
        const voiceFemale = (selectedTtsProvider === 'edge') ? selectedEdgeFemale : (selectedTtsProvider === 'gemini' ? selectedGeminiFemale : selectedGoogleFemale);
        const voiceMale = (selectedTtsProvider === 'edge') ? selectedEdgeMale : (selectedTtsProvider === 'gemini' ? selectedGeminiMale : selectedGoogleMale);
        const ttsSpeedEl = document.getElementById('ttsSpeed');
        const ttsSpeed = ttsSpeedEl ? parseFloat(ttsSpeedEl.value) : 1.2;
        const contextEl = document.getElementById('videoContext');
        const context = contextEl ? contextEl.value.trim() : '';

        // Reset UI States
        submitBtn.disabled = true;
        submitBtn.querySelector('span').textContent = 'Đang xử lý...';
        processingCard.classList.remove('hidden');
        resultsCard.classList.add('hidden');
        ocrSelectionCard.classList.add('hidden');

        // Dừng và reset tất cả video player đang phát
        [originalVideoPlayer, translatedVideoPlayer, ocrVideoPlayer].forEach(player => {
            if (player) {
                player.pause();
                player.removeAttribute('src');
                player.load();
            }
        });
        currentJobId = null;

        // Reset steps nodes
        document.querySelectorAll('.step-node').forEach(node =>
            node.classList.remove('active', 'completed')
        );
        progressLineFill.style.width = '0%';

        // Reset Terminal Logs
        terminalBody.innerHTML = '';
        appendLogLine('Sản phẩm khởi động. Đang gửi yêu cầu dịch thuật tới máy chủ...', 'info');
        displayedLogCount = 0;

        try {
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url,
                    bg_volume: bgVolume,
                    burn_subtitles: burnSubtitles,
                    tts_provider: ttsProvider,
                    asr_mode: asrMode,
                    translate_provider: translateProvider,
                    process_mode: processMode,
                    voice_name: voiceName ? voiceName : null,
                    voice_female: voiceFemale || null,
                    voice_male: voiceMale || null,
                    tts_speed: ttsSpeed,
                    translate_style: selectedTranslateStyle,
                    context: context || null
                })
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => null);
                const errMsg = (errData && errData.detail) ? errData.detail : 'Lỗi phản hồi từ máy chủ.';
                throw new Error(errMsg);
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

            // 4. Handle Completion/Failure / OCR Selection
            if (data.status === 'awaiting_ocr_selection') {
                clearInterval(pollInterval);
                currentJobId = jobId;

                // Show OCR panel and load video
                processingCard.classList.add('hidden');
                ocrSelectionCard.classList.remove('hidden');

                const videoUrl = data.result.original_video_url;
                ocrVideoPlayer.src = videoUrl;
                ocrVideoPlayer.load();

                appendLogLine('Video gốc đã tải xong. Hãy kéo chỉnh dải màu sáng đè lên khu vực chạy chữ phụ đề của video và nhấn "Bắt đầu quét OCR phụ đề".', 'success');

                // Smooth scroll to OCR Selection Workspace và tính lại kích thước phủ hợp video
                setTimeout(() => {
                    ocrSelectionCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    if (typeof updateOverlaySize === 'function') updateOverlaySize();
                }, 300);
                setTimeout(() => {
                    if (typeof updateOverlaySize === 'function') updateOverlaySize();
                }, 800);

            } else if (data.status === 'completed') {
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

    // Dynamic overlay resizing to match actual rendered video dimensions (handling letterboxing)
    function getRenderedVideoSize(videoEl) {
        const videoRatio = videoEl.videoWidth / videoEl.videoHeight;
        const width = videoEl.clientWidth;
        const height = videoEl.clientHeight;
        const elementRatio = width / height;

        let renderedWidth, renderedHeight;
        if (elementRatio > videoRatio) {
            // Rendered video is limited by height (has letterboxes on left/right)
            renderedHeight = height;
            renderedWidth = height * videoRatio;
        } else {
            // Rendered video is limited by width (has letterboxes on top/bottom)
            renderedWidth = width;
            renderedHeight = width / videoRatio;
        }

        return {
            width: renderedWidth,
            height: renderedHeight,
            top: (height - renderedHeight) / 2,
            left: (width - renderedWidth) / 2
        };
    }

    function updateOverlaySize() {
        if (!ocrVideoPlayer.videoWidth || !ocrVideoPlayer.videoHeight) return;
        const size = getRenderedVideoSize(ocrVideoPlayer);

        ocrCropOverlay.style.width = `${size.width}px`;
        ocrCropOverlay.style.height = `${size.height}px`;
        ocrCropOverlay.style.top = `${size.top}px`;
        ocrCropOverlay.style.left = `${size.left}px`;
    }

    ocrVideoPlayer.addEventListener('loadedmetadata', updateOverlaySize);
    ocrVideoPlayer.addEventListener('canplay', updateOverlaySize);
    ocrVideoPlayer.addEventListener('play', updateOverlaySize);
    window.addEventListener('resize', updateOverlaySize);

    // Crop selection box dragging/resizing logic
    const ocrCropOverlay = document.getElementById('ocrCropOverlay');
    const ocrCropBox = document.getElementById('ocrCropBox');
    let isDragging = false;
    let dragType = 'move'; // 'move', 'resize-top', 'resize-bottom'
    let startY = 0;
    let startTop = 85;   // percentage
    let startHeight = 8; // percentage

    ocrCropBox.addEventListener('mousedown', (e) => {
        isDragging = true;
        startY = e.clientY;

        const rect = ocrCropBox.getBoundingClientRect();
        const clickY = e.clientY - rect.top;
        if (clickY <= 15) {
            dragType = 'resize-top';
        } else if (clickY >= rect.height - 15) {
            dragType = 'resize-bottom';
        } else {
            dragType = 'move';
        }

        startTop = parseFloat(ocrCropBox.style.top || '85');
        startHeight = parseFloat(ocrCropBox.style.height || '8');

        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const overlayRect = ocrCropOverlay.getBoundingClientRect();
        const deltaY = ((e.clientY - startY) / overlayRect.height) * 100;

        if (dragType === 'move') {
            let newTop = startTop + deltaY;
            newTop = Math.max(0, Math.min(100 - startHeight, newTop));
            ocrCropBox.style.top = `${newTop}%`;
        } else if (dragType === 'resize-top') {
            let newTop = startTop + deltaY;
            let newHeight = startHeight - deltaY;
            if (newTop >= 0 && newHeight >= 5) {
                ocrCropBox.style.top = `${newTop}%`;
                ocrCropBox.style.height = `${newHeight}%`;
            }
        } else if (dragType === 'resize-bottom') {
            let newHeight = startHeight + deltaY;
            if (startTop + newHeight <= 100 && newHeight >= 5) {
                ocrCropBox.style.height = `${newHeight}%`;
            }
        }
    });

    document.addEventListener('mouseup', () => {
        isDragging = false;
    });

    // Touch support for dragging on mobile devices
    ocrCropBox.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) return;
        isDragging = true;
        const touch = e.touches[0];
        startY = touch.clientY;

        const rect = ocrCropBox.getBoundingClientRect();
        const clickY = touch.clientY - rect.top;
        if (clickY <= 20) {
            dragType = 'resize-top';
        } else if (clickY >= rect.height - 20) {
            dragType = 'resize-bottom';
        } else {
            dragType = 'move';
        }

        startTop = parseFloat(ocrCropBox.style.top || '85');
        startHeight = parseFloat(ocrCropBox.style.height || '8');

        e.preventDefault();
    });

    document.addEventListener('touchmove', (e) => {
        if (!isDragging || e.touches.length !== 1) return;
        const touch = e.touches[0];
        const overlayRect = ocrCropOverlay.getBoundingClientRect();
        const deltaY = ((touch.clientY - startY) / overlayRect.height) * 100;

        if (dragType === 'move') {
            let newTop = startTop + deltaY;
            newTop = Math.max(0, Math.min(100 - startHeight, newTop));
            ocrCropBox.style.top = `${newTop}%`;
        } else if (dragType === 'resize-top') {
            let newTop = startTop + deltaY;
            let newHeight = startHeight - deltaY;
            if (newTop >= 0 && newHeight >= 5) {
                ocrCropBox.style.top = `${newTop}%`;
                ocrCropBox.style.height = `${newHeight}%`;
            }
        } else if (dragType === 'resize-bottom') {
            let newHeight = startHeight + deltaY;
            if (startTop + newHeight <= 100 && newHeight >= 5) {
                ocrCropBox.style.height = `${newHeight}%`;
            }
        }
    });

    document.addEventListener('touchend', () => {
        isDragging = false;
    });

    // Resume execution handler
    async function resumeJob(jobId, useOcr) {
        ocrSelectionCard.classList.add('hidden');
        processingCard.classList.remove('hidden');

        const y_start = parseFloat(ocrCropBox.style.top || '85') / 100;
        const y_height = parseFloat(ocrCropBox.style.height || '8') / 100;
        const y_end = y_start + y_height;
        const x_start = parseFloat(ocrCropBox.style.left || '0') / 100;
        const x_width = parseFloat(ocrCropBox.style.width || '100') / 100;
        const x_end = x_start + x_width;

        appendLogLine(`[GỬI CẤU HÌNH] Chạy quy trình tiếp tục: Dùng OCR = ${useOcr}, XY = [${x_start.toFixed(2)}-${x_end.toFixed(2)}, ${y_start.toFixed(2)}-${y_end.toFixed(2)}]`, 'info');

        try {
            const response = await fetch(`/api/translate/resume/${jobId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    use_ocr: useOcr,
                    y_start: y_start,
                    y_end: y_end,
                    x_start: x_start,
                    x_end: x_end
                })
            });

            if (!response.ok) {
                throw new Error('Lỗi phản hồi từ máy chủ.');
            }

            // Re-start status polling
            displayedLogCount = 0; // reset logs display
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => pollJobStatus(jobId), 1200);

        } catch (err) {
            appendLogLine(`Lỗi khi tiếp tục tiến trình: ${err.message}`, 'error');
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = 'Bắt đầu tiến trình xử lý';
        }
    }

    btnStartOcr.addEventListener('click', () => {
        if (currentJobId) resumeJob(currentJobId, true);
    });

    btnSkipOcr.addEventListener('click', () => {
        if (currentJobId) resumeJob(currentJobId, false);
    });

    // Custom timeline controller logic
    const btnOcrPlayPause = document.getElementById('btnOcrPlayPause');
    const ocrTimelineSlider = document.getElementById('ocrTimelineSlider');
    const ocrTimeCurrent = document.getElementById('ocrTimeCurrent');
    const ocrTimeDuration = document.getElementById('ocrTimeDuration');

    function formatTime(secs) {
        if (isNaN(secs) || secs === Infinity) return '0:00';
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60);
        return `${m}:${s < 10 ? '0' : ''}${s}`;
    }

    ocrVideoPlayer.addEventListener('timeupdate', () => {
        if (!ocrVideoPlayer.duration) return;
        const percent = (ocrVideoPlayer.currentTime / ocrVideoPlayer.duration) * 100;
        ocrTimelineSlider.value = percent;
        ocrTimeCurrent.textContent = formatTime(ocrVideoPlayer.currentTime);
    });

    ocrVideoPlayer.addEventListener('durationchange', () => {
        ocrTimeDuration.textContent = formatTime(ocrVideoPlayer.duration);
    });

    ocrVideoPlayer.addEventListener('loadedmetadata', () => {
        ocrTimeDuration.textContent = formatTime(ocrVideoPlayer.duration);
    });

    ocrTimelineSlider.addEventListener('input', () => {
        if (!ocrVideoPlayer.duration) return;
        const newTime = (ocrTimelineSlider.value / 100) * ocrVideoPlayer.duration;
        ocrVideoPlayer.currentTime = newTime;
    });

    btnOcrPlayPause.addEventListener('click', () => {
        if (ocrVideoPlayer.paused) {
            ocrVideoPlayer.play();
        } else {
            ocrVideoPlayer.pause();
        }
    });

    ocrVideoPlayer.addEventListener('pause', () => {
        btnOcrPlayPause.querySelector('span').textContent = 'Phát video';
    });

    ocrVideoPlayer.addEventListener('play', () => {
        btnOcrPlayPause.querySelector('span').textContent = 'Tạm dừng';
    });

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
