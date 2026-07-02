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

    const activeGlossaryBadge = document.getElementById('activeGlossaryBadge');
    const styleNameMap = {
        'default': 'Mặc định (Default)',
        'dialogue': 'Phim ảnh (Dialogue)',
        'review': 'Review / Vlog',
        'tutorial': 'Hướng dẫn (Tutorial)'
    };
    function updateActiveGlossaryBadge(style) {
        if (activeGlossaryBadge) {
            const name = styleNameMap[style] || style;
            activeGlossaryBadge.textContent = `Từ điển: ${name}`;
        }
    }
    updateActiveGlossaryBadge(selectedTranslateStyle);

    // Style Toggle Buttons
    styleToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            styleToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedTranslateStyle = btn.dataset.style;
            updateActiveGlossaryBadge(selectedTranslateStyle);
        });
    });

    const btnGetCookieDouyin = document.getElementById('btnGetCookieDouyin');
    const btnGetCookieBilibili = document.getElementById('btnGetCookieBilibili');
    const btnGetCookieYoutube = document.getElementById('btnGetCookieYoutube');

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

    // Handle burnSubtitles checkbox -> toggle sub style panel
    const subStylePanel = document.getElementById('subStylePanel');
    if (burnSubtitlesCheckbox && subStylePanel) {
        burnSubtitlesCheckbox.addEventListener('change', () => {
            subStylePanel.style.display = burnSubtitlesCheckbox.checked ? 'block' : 'none';
        });
    }

    // Handle context toggle button
    const btnToggleContext = document.getElementById('btnToggleContext');
    const contextGroup = document.getElementById('contextGroup');
    if (btnToggleContext && contextGroup) {
        btnToggleContext.addEventListener('click', () => {
            const isVisible = contextGroup.style.display !== 'none';
            contextGroup.style.display = isVisible ? 'none' : 'block';
            btnToggleContext.textContent = isVisible ? '+ Bối cảnh' : '− Bối cảnh';
            btnToggleContext.classList.toggle('active', !isVisible);
        });
    }

    // Handle subtitle style toggle button
    const btnToggleSubStyle = document.getElementById('btnToggleSubStyle');
    const subStyleCompact = document.getElementById('subStyleCompact');
    const subPreviewArea = document.getElementById('subPreviewArea');
    const subPreviewText = document.getElementById('subPreviewText');

    if (btnToggleSubStyle && subStyleCompact) {
        btnToggleSubStyle.addEventListener('click', () => {
            const isVisible = subStyleCompact.style.display !== 'none';
            subStyleCompact.style.display = isVisible ? 'none' : 'block';
            btnToggleSubStyle.textContent = isVisible ? '+ Mở' : '− Đóng';
            btnToggleSubStyle.classList.toggle('active', !isVisible);
        });
    }

    // Aspect ratio buttons
    document.querySelectorAll('.aspect-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.aspect-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const aspect = btn.dataset.aspect;
            if (subPreviewArea) {
                subPreviewArea.className = 'sub-preview-area aspect-' + aspect.replace(':', '-');
            }
        });
    });

    // Live preview update
    function updateSubPreview() {
        if (!subPreviewText || !subPreviewArea) return;
        const font = document.getElementById('subFont')?.value || 'Montserrat';
        const size = document.getElementById('subFontSize')?.value || '20';
        const colorEl = document.getElementById('subColor');
        const pos = document.getElementById('subPosition')?.value || '2';
        const outline = document.getElementById('subOutline')?.value || '1.5';
        const bgAlpha = document.getElementById('subBgAlpha')?.value || '80';

        subPreviewText.style.fontFamily = font + ', sans-serif';
        subPreviewText.style.fontSize = size + 'px';
        subPreviewText.style.textShadow = `0 0 ${outline}px #000, 0 0 ${parseFloat(outline) * 2}px #000`;

        // Map color
        const colorMap = { '&H00FFFFFF': '#FFFFFF', '&H0000FFFF': '#FFFF00', '&H0000FF00': '#00FF00', '&H00FF0000': '#0066FF', '&H000000FF': '#FF0000', '&H00FF80FF': '#FF80FF' };
        subPreviewText.style.color = colorMap[colorEl?.value] || '#FFFFFF';

        // Background
        const alpha = parseInt(bgAlpha, 16);
        subPreviewText.style.background = alpha > 0 ? `rgba(0,0,0,${alpha / 255})` : 'transparent';

        // Position
        const posMap = { '2': 'flex-end', '1': 'flex-end', '3': 'flex-end', '8': 'flex-start', '5': 'center' };
        const justifyMap = { '2': 'center', '1': 'flex-start', '3': 'flex-end', '8': 'center', '5': 'center' };
        subPreviewArea.style.alignItems = posMap[pos] || 'flex-end';
        subPreviewArea.style.justifyContent = justifyMap[pos] || 'center';
    }

    document.querySelectorAll('#subStyleCompact select').forEach(sel => {
        sel.addEventListener('change', updateSubPreview);
    });

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

    // Handle dynamic cookie login buttons
    async function handleLogin(btn, platform) {
        if (!btn) return;
        btn.disabled = true;
        const spanText = btn.querySelector('span');
        const originalText = spanText.textContent;
        spanText.textContent = 'Đang xác thực...';

        processingCard.classList.remove('hidden');
        appendLogLine(`Đang gửi yêu cầu mở trình duyệt đăng nhập ${platform === 'douyin' ? 'Douyin' : 'Bilibili'}...`, 'info');

        try {
            const response = await fetch(`/api/get-cookies?platform=${platform}`, {
                method: 'POST'
            });
            const data = await response.json();
            if (data.status === 'success') {
                appendLogLine(`[ĐĂNG NHẬP] ${data.message}`, 'success');
                alert(`Đăng nhập thành công!\n${data.message}`);
            } else {
                appendLogLine(`[ĐĂNG NHẬP THẤT BẠI] ${data.message}`, 'error');
                alert(`Không thể lấy cookie: ${data.message}`);
            }
        } catch (err) {
            appendLogLine(`[ĐĂNG NHẬP LỖI] Lỗi kết nối server: ${err.message}`, 'error');
            alert(`Lỗi kết nối tới máy chủ khi yêu cầu lấy cookie.`);
        } finally {
            btn.disabled = false;
            spanText.textContent = originalText;
        }
    }

    if (btnGetCookieDouyin) {
        btnGetCookieDouyin.addEventListener('click', () => handleLogin(btnGetCookieDouyin, 'douyin'));
    }
    if (btnGetCookieBilibili) {
        btnGetCookieBilibili.addEventListener('click', () => handleLogin(btnGetCookieBilibili, 'bilibili'));
    }
    if (btnGetCookieYoutube) {
        btnGetCookieYoutube.addEventListener('click', () => handleLogin(btnGetCookieYoutube, 'youtube'));
    }

    // ─── Import file button inside URL input ───────────────────────────
    const btnImportFile = document.getElementById('btnImportFile');
    const videoFileInput = document.getElementById('videoFileInput');
    const fileBadge = document.getElementById('fileSelectedBadge');
    const fileNameEl = document.getElementById('selectedFileName');
    const fileRemoveBtn = document.getElementById('fileRemoveBtn');
    let importedFilePath = null;
    let importedSrtPath = null;
    let detectedSrtPath = null;
    let originalFilename = null;

    const srtSelectedBadge = document.getElementById('srtSelectedBadge');
    const selectedSrtName = document.getElementById('selectedSrtName');
    const srtRemoveBtn = document.getElementById('srtRemoveBtn');
    const srtUploadContainer = document.getElementById('srtUploadContainer');
    const btnSelectSrtManual = document.getElementById('btnSelectSrtManual');
    const srtFileInput = document.getElementById('srtFileInput');

    btnImportFile.addEventListener('click', (e) => {
        e.stopPropagation();
        videoFileInput.click();
    });

    videoFileInput.addEventListener('change', async () => {
        if (videoFileInput.files.length > 0) {
            const files = Array.from(videoFileInput.files);
            // Tìm file video và file srt trong tập hợp các file được chọn
            const videoFile = files.find(file => {
                const ext = file.name.split('.').pop().toLowerCase();
                return ['mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv'].includes(ext);
            });
            const srtFile = files.find(file => {
                const ext = file.name.split('.').pop().toLowerCase();
                return ext === 'srt';
            });

            if (videoFile) {
                // Tải video lên trước
                await uploadFile(videoFile);
                
                // Nếu có file srt đi kèm
                if (srtFile) {
                    await uploadSrtFile(srtFile);
                }
            } else if (srtFile) {
                // Nếu chỉ chọn mỗi file phụ đề
                await uploadSrtFile(srtFile);
            }
        }
    });

    if (btnSelectSrtManual) {
        btnSelectSrtManual.addEventListener('click', (e) => {
            e.stopPropagation();
            srtFileInput.click();
        });
    }

    if (srtFileInput) {
        srtFileInput.addEventListener('change', async () => {
            if (srtFileInput.files.length > 0) {
                await uploadSrtFile(srtFileInput.files[0]);
            }
        });
    }

    if (srtRemoveBtn) {
        srtRemoveBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            importedSrtPath = null;
            detectedSrtPath = null;
            srtFileInput.value = '';
            srtSelectedBadge.classList.add('hidden');
            srtUploadContainer.classList.remove('hidden');
            appendLogLine('[PHỤ ĐỀ] Đã bỏ qua file phụ đề cũ. Hệ thống sẽ quét OCR và dịch lại từ đầu.', 'info');
        });
    }

    fileRemoveBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        importedFilePath = null;
        importedSrtPath = null;
        detectedSrtPath = null;
        originalFilename = null;
        videoFileInput.value = '';
        if (srtFileInput) srtFileInput.value = '';
        fileBadge.classList.add('hidden');
        if (srtSelectedBadge) srtSelectedBadge.classList.add('hidden');
        if (srtUploadContainer) srtUploadContainer.classList.remove('hidden');
        
        videoUrlInput.required = true;
        videoUrlInput.removeAttribute('disabled');
        videoUrlInput.placeholder = 'Dán liên kết Douyin, Bilibili, YouTube hoặc chọn file video...';
    });

    async function uploadFile(file) {
        if (file.size > 4 * 1024 * 1024 * 1024) {
            alert('File quá lớn! Tối đa 4GB.');
            return;
        }
        originalFilename = file.name;
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        fileNameEl.textContent = file.name + ' (' + sizeMB + ' MB)';
        fileBadge.classList.remove('hidden');
        videoUrlInput.required = false;
        videoUrlInput.setAttribute('disabled', 'disabled');

        try {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch('/api/upload-video', { method: 'POST', body: formData });
            if (!resp.ok) throw new Error((await resp.json().catch(() => null))?.detail || 'Upload thất bại');
            const data = await resp.json();
            importedFilePath = data.path;
            fileNameEl.textContent = file.name + ' (' + data.size_mb + ' MB OK)';
            appendLogLine('[IMPORT VIDEO] ' + file.name + ' (' + data.size_mb + ' MB)', 'success');

            // Xử lý phụ đề phát hiện tự động từ projects/
            if (data.detected_srt) {
                detectedSrtPath = data.detected_srt;
                selectedSrtName.textContent = 'Phụ đề: ' + data.detected_srt.split(/[\\/]/).pop() + ' (Tự động phát hiện)';
                srtSelectedBadge.classList.remove('hidden');
                srtUploadContainer.classList.add('hidden');
                appendLogLine('[SRT PHÁT HIỆN] Phát hiện phụ đề trùng tên trong dự án: ' + data.detected_srt + '. Nhấn Bỏ (X) nếu muốn dịch lại.', 'info');
            } else {
                detectedSrtPath = null;
                srtSelectedBadge.classList.add('hidden');
                srtUploadContainer.classList.remove('hidden');
            }
        } catch (err) {
            fileNameEl.textContent = 'Lỗi: ' + err.message;
            appendLogLine('[IMPORT LỖI] ' + err.message, 'error');
        }
    }

    async function uploadSrtFile(file) {
        selectedSrtName.textContent = file.name + ' (Đang tải lên...)';
        srtSelectedBadge.classList.remove('hidden');
        srtUploadContainer.classList.add('hidden');

        try {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch('/api/upload-srt', { method: 'POST', body: formData });
            if (!resp.ok) throw new Error((await resp.json().catch(() => null))?.detail || 'Upload SRT thất bại');
            const data = await resp.json();
            importedSrtPath = data.path;
            selectedSrtName.textContent = 'Phụ đề: ' + file.name + ' (Đã nạp)';
            appendLogLine('[IMPORT SRT] ' + file.name + ' thành công.', 'success');
        } catch (err) {
            selectedSrtName.textContent = 'Lỗi nạp SRT: ' + err.message;
            appendLogLine('[IMPORT SRT LỖI] ' + err.message, 'error');
        }
    }

    function getContextValue() {
        const el = document.getElementById('videoContext');
        return el ? el.value.trim() : '';
    }

    // Mode selector registration
    let activeMode = 'single';
    const tabModeSingle = document.getElementById('tabModeSingle');
    const tabModeBatch = document.getElementById('tabModeBatch');
    const videoUrls = document.getElementById('videoUrls');
    const batchProcessingCard = document.getElementById('batchProcessingCard');

    if (tabModeSingle && tabModeBatch && videoUrls) {
        tabModeSingle.addEventListener('click', () => {
            activeMode = 'single';
            tabModeSingle.classList.add('active');
            tabModeSingle.style.borderBottom = '2px solid var(--accent)';
            tabModeSingle.style.color = 'var(--accent)';
            tabModeBatch.classList.remove('active');
            tabModeBatch.style.borderBottom = '2px solid transparent';
            tabModeBatch.style.color = 'var(--text-muted)';
            
            videoUrlInput.classList.remove('hidden');
            videoUrlInput.style.display = 'block';
            videoUrlInput.required = !importedFilePath;
            
            videoUrls.classList.add('hidden');
            videoUrls.style.display = 'none';
            videoUrls.required = false;
        });

        tabModeBatch.addEventListener('click', () => {
            activeMode = 'batch';
            tabModeBatch.classList.add('active');
            tabModeBatch.style.borderBottom = '2px solid var(--accent)';
            tabModeBatch.style.color = 'var(--accent)';
            tabModeSingle.classList.remove('active');
            tabModeSingle.style.borderBottom = '2px solid transparent';
            tabModeSingle.style.color = 'var(--text-muted)';
            
            videoUrlInput.classList.add('hidden');
            videoUrlInput.style.display = 'none';
            videoUrlInput.required = false;
            
            videoUrls.classList.remove('hidden');
            videoUrls.style.display = 'block';
            videoUrls.required = true;
        });
    }

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (activeMode === 'batch') {
            const urlsRaw = videoUrls.value.split('\n');
            const urls = urlsRaw.map(u => u.trim()).filter(u => u.length > 0);
            if (urls.length === 0) {
                alert('Vui lòng nhập ít nhất một liên kết video!');
                return;
            }

            // UI Reset for Batch
            submitBtn.disabled = true;
            submitBtn.querySelector('span').textContent = 'Đang chạy batch...';
            batchProcessingCard.classList.remove('hidden');
            processingCard.classList.add('hidden');
            resultsCard.classList.add('hidden');
            ocrSelectionCard.classList.add('hidden');

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
            const ttsSpeed = ttsSpeedEl ? parseFloat(ttsSpeedEl.value) : 1.4;
            const context = getContextValue();

            // Clear terminal batch log
            const batchTerminal = document.getElementById('batchTerminalBody');
            if (batchTerminal) batchTerminal.innerHTML = 'Đang khởi động tiến trình dịch thuật hàng loạt...\n';
            displayedBatchLogCount = 0;

            try {
                const response = await fetch('/api/translate/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        urls: urls,
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
                        context: context || null,
                        resolution: document.getElementById('videoResolution') ? document.getElementById('videoResolution').value : '1080',
                        subtitle_style: burnSubtitlesCheckbox.checked ? {
                            font: (document.getElementById('subFont') || {}).value || 'Montserrat',
                            fontsize: parseInt((document.getElementById('subFontSize') || {}).value) || 20,
                            color: (document.getElementById('subColor') || {}).value || '&H00FFFFFF',
                            position: parseInt((document.getElementById('subPosition') || {}).value) || 2
                        } : null
                    })
                });

                if (!response.ok) {
                    const errData = await response.json().catch(() => null);
                    throw new Error((errData && errData.detail) ? errData.detail : 'Lỗi kết nối máy chủ.');
                }

                const data = await response.json();
                const batchId = data.batch_id;

                if (pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(() => pollBatchStatus(batchId), 1200);

            } catch (err) {
                alert(`Lỗi khởi chạy tiến trình hàng loạt: ${err.message}`);
                submitBtn.disabled = false;
                submitBtn.querySelector('span').textContent = 'Bắt đầu tiến trình xử lý';
            }
            return;
        }

        const url = videoUrlInput.value.trim();
        if (!url && !importedFilePath) return;

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
        const ttsSpeed = ttsSpeedEl ? parseFloat(ttsSpeedEl.value) : 1.4;
        const context = getContextValue();

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
                    url: importedFilePath ? '' : url,
                    imported_file: importedFilePath || null,
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
                    context: context || null,
                    resolution: document.getElementById('videoResolution') ? document.getElementById('videoResolution').value : '1080',
                    imported_srt: importedSrtPath || null,
                    use_detected_srt: (detectedSrtPath) ? true : false,
                    original_filename: originalFilename || null,
                    subtitle_style: burnSubtitlesCheckbox.checked ? {
                        font: (document.getElementById('subFont') || {}).value || 'Montserrat',
                        fontsize: parseInt((document.getElementById('subFontSize') || {}).value) || 20,
                        color: (document.getElementById('subColor') || {}).value || '&H00FFFFFF',
                        position: parseInt((document.getElementById('subPosition') || {}).value) || 2
                    } : null
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

    let displayedBatchLogCount = 0;
    async function pollBatchStatus(batchId) {
        try {
            const response = await fetch(`/api/status/${batchId}`);
            if (!response.ok) throw new Error('Không thể lấy trạng thái batch.');
            const data = await response.json();

            // 1. Update overall status badge
            const overallStatus = document.getElementById('batchOverallStatus');
            if (overallStatus) {
                overallStatus.textContent = data.status === 'running' ? 'Đang chạy...' : (data.status === 'completed' ? 'Đã hoàn thành' : 'Thất bại');
                overallStatus.className = 'badge ' + (data.status === 'running' ? 'badge-running' : (data.status === 'completed' ? 'badge-completed' : 'badge-failed'));
            }

            // 2. Update progress bar
            const total = data.items.length;
            const completedCount = data.items.filter(i => i.status === 'completed').length;
            const failedCount = data.items.filter(i => i.status === 'failed').length;
            const processed = completedCount + failedCount;
            const percent = total > 0 ? Math.round((processed / total) * 100) : 0;

            const progressText = document.getElementById('batchProgressText');
            if (progressText) {
                progressText.textContent = `Tiến độ: Video ${data.current_index + 1}/${total} (Đã hoàn thành ${completedCount}, Lỗi ${failedCount})`;
            }
            const percentText = document.getElementById('batchPercentText');
            if (percentText) {
                percentText.textContent = `${percent}%`;
            }
            const barFill = document.getElementById('batchProgressBarFill');
            if (barFill) {
                barFill.style.width = `${percent}%`;
            }

            // 3. Render items list with individual download buttons!
            const listContainer = document.getElementById('batchItemsList');
            if (listContainer) {
                listContainer.innerHTML = '';
                data.items.forEach((item, index) => {
                    const row = document.createElement('div');
                    row.style.display = 'flex';
                    row.style.justifyContent = 'space-between';
                    row.style.alignItems = 'center';
                    row.style.padding = '8px 12px';
                    row.style.background = 'rgba(255,255,255,0.02)';
                    row.style.border = '1px solid var(--border)';
                    row.style.borderRadius = '6px';
                    
                    const left = document.createElement('div');
                    left.style.display = 'flex';
                    left.style.flexDirection = 'column';
                    left.style.gap = '2px';
                    
                    const title = document.createElement('span');
                    title.style.fontSize = '0.85rem';
                    title.style.fontWeight = '500';
                    title.style.color = index === data.current_index && data.status === 'running' ? 'var(--accent)' : 'var(--text)';
                    
                    let urlLabel = item.url;
                    if (urlLabel.length > 60) urlLabel = urlLabel.substring(0, 60) + '...';
                    title.textContent = `${index + 1}. ${urlLabel}`;
                    
                    const statusText = document.createElement('span');
                    statusText.style.fontSize = '0.75rem';
                    if (item.status === 'waiting') {
                        statusText.textContent = '⏳ Đang chờ...';
                        statusText.style.color = 'var(--text-muted)';
                    } else if (item.status === 'running') {
                        statusText.textContent = '🔄 Đang xử lý...';
                        statusText.style.color = 'var(--accent)';
                    } else if (item.status === 'completed') {
                        statusText.textContent = '✅ Đã hoàn thành';
                        statusText.style.color = '#10b981';
                    } else if (item.status === 'failed') {
                        statusText.textContent = `❌ Lỗi: ${item.error || 'Thất bại'}`;
                        statusText.style.color = '#ef4444';
                    }
                    
                    left.appendChild(title);
                    left.appendChild(statusText);
                    row.appendChild(left);

                    if (item.status === 'completed' && item.result) {
                        const right = document.createElement('div');
                        right.style.display = 'flex';
                        right.style.gap = '6px';
                        
                        if (item.result.translated_video_url) {
                            const btnDl = document.createElement('a');
                            btnDl.href = item.result.translated_video_url;
                            btnDl.download = `translated_${index + 1}.mp4`;
                            btnDl.textContent = '📥 Tải video';
                            btnDl.style.fontSize = '0.75rem';
                            btnDl.style.padding = '4px 8px';
                            btnDl.style.background = 'var(--accent)';
                            btnDl.style.color = 'white';
                            btnDl.style.borderRadius = '4px';
                            btnDl.style.textDecoration = 'none';
                            right.appendChild(btnDl);
                        }
                        if (item.result.srt_url) {
                            const btnSrt = document.createElement('a');
                            btnSrt.href = item.result.srt_url;
                            btnSrt.download = `subtitles_${index + 1}.srt`;
                            btnSrt.textContent = '📝 SRT';
                            btnSrt.style.fontSize = '0.75rem';
                            btnSrt.style.padding = '4px 8px';
                            btnSrt.style.background = 'rgba(255,255,255,0.08)';
                            btnSrt.style.color = 'var(--text)';
                            btnSrt.style.borderRadius = '4px';
                            btnSrt.style.border = '1px solid var(--border)';
                            btnSrt.style.textDecoration = 'none';
                            right.appendChild(btnSrt);
                        }
                        row.appendChild(right);
                    }
                    
                    listContainer.appendChild(row);
                });
            }

            const terminal = document.getElementById('batchTerminalBody');
            if (terminal) {
                const logs = data.logs || [];
                if (logs.length > displayedBatchLogCount) {
                    if (displayedBatchLogCount === 0) terminal.innerHTML = '';
                    for (let i = displayedBatchLogCount; i < logs.length; i++) {
                        const line = logs[i];
                        const div = document.createElement('div');
                        div.style.marginBottom = '2px';
                        
                        if (line.includes('LỖI') || line.includes('ERROR') || line.includes('Thất bại')) {
                            div.style.color = '#f87171';
                        } else if (line.includes('thành công') || line.includes('Hoàn thành') || line.includes('SUCCESS')) {
                            div.style.color = '#34d399';
                        } else if (line.includes('Cảnh báo') || line.includes('WARNING')) {
                            div.style.color = '#fbbf24';
                        }
                        div.textContent = line;
                        terminal.appendChild(div);
                    }
                    displayedBatchLogCount = logs.length;
                    terminal.scrollTop = terminal.scrollHeight;
                }
            }

            if (data.status !== 'running') {
                clearInterval(pollInterval);
                pollInterval = null;
                submitBtn.disabled = false;
                submitBtn.querySelector('span').textContent = 'Bắt đầu tiến trình xử lý';
            }

        } catch (err) {
            console.error('Lỗi khi cập nhật trạng thái batch:', err);
        }
    }

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

                // Khởi tạo kích thước mặc định cho khung chọn OCR 2 chiều
                ocrCropBox.style.left = '10%';
                ocrCropBox.style.width = '80%';
                ocrCropBox.style.top = '85%';
                ocrCropBox.style.height = '8%';

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

            } else if (data.status === 'awaiting_subtitle_review') {
                clearInterval(pollInterval);
                currentJobId = jobId;
                showSubtitleReviewModal(data);

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
    const ocrGuideVertical = document.getElementById('ocrGuideVertical');
    const ocrGuideHorizontal = document.getElementById('ocrGuideHorizontal');
    let isDragging = false;
    let dragType = 'move'; // 'move', 'resize-top', 'resize-bottom', 'resize-left', 'resize-right', etc.
    let startX = 0;
    let startY = 0;
    let startTop = 85;   // percentage
    let startHeight = 8; // percentage
    let startLeft = 10;   // percentage
    let startWidth = 80; // percentage

    ocrCropBox.addEventListener('mousedown', (e) => {
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;

        const rect = ocrCropBox.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const clickY = e.clientY - rect.top;

        // Xác định kéo cạnh nào (ngưỡng 12px)
        const border = 12;
        const isLeft = clickX <= border;
        const isRight = clickX >= rect.width - border;
        const isTop = clickY <= border;
        const isBottom = clickY >= rect.height - border;

        if (isLeft && isTop) dragType = 'resize-topleft';
        else if (isRight && isTop) dragType = 'resize-topright';
        else if (isLeft && isBottom) dragType = 'resize-bottomleft';
        else if (isRight && isBottom) dragType = 'resize-bottomright';
        else if (isLeft) dragType = 'resize-left';
        else if (isRight) dragType = 'resize-right';
        else if (isTop) dragType = 'resize-top';
        else if (isBottom) dragType = 'resize-bottom';
        else dragType = 'move';

        startTop = parseFloat(ocrCropBox.style.top || '85');
        startHeight = parseFloat(ocrCropBox.style.height || '8');
        startLeft = parseFloat(ocrCropBox.style.left || '10');
        startWidth = parseFloat(ocrCropBox.style.width || '80');

        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const overlayRect = ocrCropOverlay.getBoundingClientRect();
        const deltaX = ((e.clientX - startX) / overlayRect.width) * 100;
        const deltaY = ((e.clientY - startY) / overlayRect.height) * 100;

        if (dragType === 'move') {
            let newTop = startTop + deltaY;
            let newLeft = startLeft + deltaX;
            newTop = Math.max(0, Math.min(100 - startHeight, newTop));
            newLeft = Math.max(0, Math.min(100 - startWidth, newLeft));

            // Căn chỉnh tâm kiểu CapCut (Snapping & Guides)
            const potentialCenterX = newLeft + startWidth / 2;
            const potentialCenterY = newTop + startHeight / 2;
            const snapThreshold = 1.5;

            // Snap & Show vertical guide (center horizontally)
            if (Math.abs(potentialCenterX - 50) < snapThreshold) {
                newLeft = 50 - startWidth / 2;
                if (ocrGuideVertical) ocrGuideVertical.classList.add('active');
            } else {
                if (ocrGuideVertical) ocrGuideVertical.classList.remove('active');
            }

            // Snap & Show horizontal guide (center vertically)
            if (Math.abs(potentialCenterY - 50) < snapThreshold) {
                newTop = 50 - startHeight / 2;
                if (ocrGuideHorizontal) ocrGuideHorizontal.classList.add('active');
            } else {
                if (ocrGuideHorizontal) ocrGuideHorizontal.classList.remove('active');
            }

            ocrCropBox.style.top = `${newTop}%`;
            ocrCropBox.style.left = `${newLeft}%`;
        } else {
            let newTop = startTop;
            let newHeight = startHeight;
            let newLeft = startLeft;
            let newWidth = startWidth;

            // Xử lý chiều dọc (Y-axis)
            if (dragType.includes('top')) {
                newTop = startTop + deltaY;
                newHeight = startHeight - deltaY;
                if (newTop < 0) {
                    newHeight = startTop + startHeight;
                    newTop = 0;
                }
            } else if (dragType.includes('bottom')) {
                newHeight = startHeight + deltaY;
                if (startTop + newHeight > 100) {
                    newHeight = 100 - startTop;
                }
            }

            // Xử lý chiều ngang (X-axis)
            if (dragType.includes('left')) {
                newLeft = startLeft + deltaX;
                newWidth = startWidth - deltaX;
                if (newLeft < 0) {
                    newWidth = startLeft + startWidth;
                    newLeft = 0;
                }
            } else if (dragType.includes('right')) {
                newWidth = startWidth + deltaX;
                if (startLeft + newWidth > 100) {
                    newWidth = 100 - startLeft;
                }
            }

            // Giới hạn kích thước tối thiểu là 4%
            const minSize = 4;
            if (newHeight >= minSize) {
                ocrCropBox.style.top = `${newTop}%`;
                ocrCropBox.style.height = `${newHeight}%`;
            }
            if (newWidth >= minSize) {
                ocrCropBox.style.left = `${newLeft}%`;
                ocrCropBox.style.width = `${newWidth}%`;
            }
        }
    });

    document.addEventListener('mouseup', () => {
        isDragging = false;
        if (ocrGuideVertical) ocrGuideVertical.classList.remove('active');
        if (ocrGuideHorizontal) ocrGuideHorizontal.classList.remove('active');
    });

    // Touch support for dragging on mobile devices
    ocrCropBox.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) return;
        isDragging = true;
        const touch = e.touches[0];
        startX = touch.clientX;
        startY = touch.clientY;

        const rect = ocrCropBox.getBoundingClientRect();
        const clickX = touch.clientX - rect.left;
        const clickY = touch.clientY - rect.top;

        // Ngưỡng to hơn một chút cho chạm tay trên di động
        const border = 16;
        const isLeft = clickX <= border;
        const isRight = clickX >= rect.width - border;
        const isTop = clickY <= border;
        const isBottom = clickY >= rect.height - border;

        if (isLeft && isTop) dragType = 'resize-topleft';
        else if (isRight && isTop) dragType = 'resize-topright';
        else if (isLeft && isBottom) dragType = 'resize-bottomleft';
        else if (isRight && isBottom) dragType = 'resize-bottomright';
        else if (isLeft) dragType = 'resize-left';
        else if (isRight) dragType = 'resize-right';
        else if (isTop) dragType = 'resize-top';
        else if (isBottom) dragType = 'resize-bottom';
        else dragType = 'move';

        startTop = parseFloat(ocrCropBox.style.top || '85');
        startHeight = parseFloat(ocrCropBox.style.height || '8');
        startLeft = parseFloat(ocrCropBox.style.left || '10');
        startWidth = parseFloat(ocrCropBox.style.width || '80');

        e.preventDefault();
    });

    document.addEventListener('touchmove', (e) => {
        if (!isDragging || e.touches.length !== 1) return;
        const touch = e.touches[0];
        const overlayRect = ocrCropOverlay.getBoundingClientRect();
        const deltaX = ((touch.clientX - startX) / overlayRect.width) * 100;
        const deltaY = ((touch.clientY - startY) / overlayRect.height) * 100;

        if (dragType === 'move') {
            let newTop = startTop + deltaY;
            let newLeft = startLeft + deltaX;
            newTop = Math.max(0, Math.min(100 - startHeight, newTop));
            newLeft = Math.max(0, Math.min(100 - startWidth, newLeft));

            // Căn chỉnh tâm kiểu CapCut (Snapping & Guides)
            const potentialCenterX = newLeft + startWidth / 2;
            const potentialCenterY = newTop + startHeight / 2;
            const snapThreshold = 1.5;

            // Snap & Show vertical guide (center horizontally)
            if (Math.abs(potentialCenterX - 50) < snapThreshold) {
                newLeft = 50 - startWidth / 2;
                if (ocrGuideVertical) ocrGuideVertical.classList.add('active');
            } else {
                if (ocrGuideVertical) ocrGuideVertical.classList.remove('active');
            }

            // Snap & Show horizontal guide (center vertically)
            if (Math.abs(potentialCenterY - 50) < snapThreshold) {
                newTop = 50 - startHeight / 2;
                if (ocrGuideHorizontal) ocrGuideHorizontal.classList.add('active');
            } else {
                if (ocrGuideHorizontal) ocrGuideHorizontal.classList.remove('active');
            }

            ocrCropBox.style.top = `${newTop}%`;
            ocrCropBox.style.left = `${newLeft}%`;
        } else {
            let newTop = startTop;
            let newHeight = startHeight;
            let newLeft = startLeft;
            let newWidth = startWidth;

            // Xử lý chiều dọc (Y-axis)
            if (dragType.includes('top')) {
                newTop = startTop + deltaY;
                newHeight = startHeight - deltaY;
                if (newTop < 0) {
                    newHeight = startTop + startHeight;
                    newTop = 0;
                }
            } else if (dragType.includes('bottom')) {
                newHeight = startHeight + deltaY;
                if (startTop + newHeight > 100) {
                    newHeight = 100 - startTop;
                }
            }

            // Xử lý chiều ngang (X-axis)
            if (dragType.includes('left')) {
                newLeft = startLeft + deltaX;
                newWidth = startWidth - deltaX;
                if (newLeft < 0) {
                    newWidth = startLeft + startWidth;
                    newLeft = 0;
                }
            } else if (dragType.includes('right')) {
                newWidth = startWidth + deltaX;
                if (startLeft + newWidth > 100) {
                    newWidth = 100 - startLeft;
                }
            }

            // Giới hạn kích thước tối thiểu là 4%
            const minSize = 4;
            if (newHeight >= minSize) {
                ocrCropBox.style.top = `${newTop}%`;
                ocrCropBox.style.height = `${newHeight}%`;
            }
            if (newWidth >= minSize) {
                ocrCropBox.style.left = `${newLeft}%`;
                ocrCropBox.style.width = `${newWidth}%`;
            }
        }
    });

    document.addEventListener('touchend', () => {
        isDragging = false;
        if (ocrGuideVertical) ocrGuideVertical.classList.remove('active');
        if (ocrGuideHorizontal) ocrGuideHorizontal.classList.remove('active');
    });

    // Resume execution handler
    async function resumeJob(jobId, useOcr) {
        ocrSelectionCard.classList.add('hidden');
        processingCard.classList.remove('hidden');

        const y_start = parseFloat(ocrCropBox.style.top || '85') / 100;
        const y_height = parseFloat(ocrCropBox.style.height || '8') / 100;
        const y_end = y_start + y_height;
        const x_start = parseFloat(ocrCropBox.style.left || '10') / 100;
        const x_width = parseFloat(ocrCropBox.style.width || '80') / 100;
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

    // --- Subtitle Review Modal controller ---
    const subtitleReviewModal = document.getElementById('subtitleReviewModal');
    const reviewCountdownContainer = document.getElementById('reviewCountdownContainer');
    const subtitleCountdownText = document.getElementById('subtitleCountdownText');
    const reviewVideoPlayer = document.getElementById('reviewVideoPlayer');
    const subtitleList = document.getElementById('subtitleList');
    const btnEditSubtitles = document.getElementById('btnEditSubtitles');
    const btnContinueTTS = document.getElementById('btnContinueTTS');

    let countdownInterval = null;
    let reviewSubtitles = [];

    function showSubtitleReviewModal(data) {
        subtitleReviewModal.classList.remove('hidden');

        // Load video
        if (data.result && data.result.original_video_url) {
            reviewVideoPlayer.src = data.result.original_video_url;
            reviewVideoPlayer.load();
        }

        reviewSubtitles = data.subtitles || [];
        renderSubtitleList(reviewSubtitles);

        // Setup countdown
        let secondsLeft = data.subtitle_review_countdown || 30;
        let isPaused = data.subtitle_review_paused || false;

        updateCountdownUI(secondsLeft, isPaused);

        if (countdownInterval) clearInterval(countdownInterval);

        if (!isPaused) {
            countdownInterval = setInterval(() => {
                secondsLeft--;
                updateCountdownUI(secondsLeft, false);
                if (secondsLeft <= 0) {
                    clearInterval(countdownInterval);
                    autoSubmitSubtitles();
                }
            }, 1000);
        }
    }

    function renderSubtitleList(subtitles) {
        subtitleList.innerHTML = '';
        subtitles.forEach((sub, index) => {
            const row = document.createElement('div');
            row.classList.add('subtitle-item-row');
            row.dataset.index = index;

            const timeDiv = document.createElement('div');
            timeDiv.classList.add('sub-time-inputs');

            const startGroup = document.createElement('div');
            startGroup.classList.add('time-input-group');
            const startLabel = document.createElement('span');
            startLabel.classList.add('time-label');
            startLabel.textContent = 'Bắt đầu';
            const startInput = document.createElement('input');
            startInput.type = 'number';
            startInput.step = '0.05';
            startInput.classList.add('sub-time-input', 'start-time-input');
            startInput.value = sub.start.toFixed(2);
            startGroup.appendChild(startLabel);
            startGroup.appendChild(startInput);

            const endGroup = document.createElement('div');
            endGroup.classList.add('time-input-group');
            const endLabel = document.createElement('span');
            endLabel.classList.add('time-label');
            endLabel.textContent = 'Kết thúc';
            const endInput = document.createElement('input');
            endInput.type = 'number';
            endInput.step = '0.05';
            endInput.classList.add('sub-time-input', 'end-time-input');
            endInput.value = sub.end.toFixed(2);
            endGroup.appendChild(endLabel);
            endGroup.appendChild(endInput);

            timeDiv.appendChild(startGroup);
            timeDiv.appendChild(endGroup);

            const textDiv = document.createElement('div');
            textDiv.classList.add('sub-text-edit-area');

            const origSpan = document.createElement('span');
            origSpan.classList.add('sub-text-original');
            origSpan.textContent = `Gốc: ${sub.text}`;

            const transInput = document.createElement('input');
            transInput.type = 'text';
            transInput.classList.add('sub-text-input', 'translation-text-input');
            transInput.value = sub.translation;

            textDiv.appendChild(origSpan);
            textDiv.appendChild(transInput);

            // Thêm vùng chọn phân vai giọng cho từng dòng phụ đề
            const speakerDiv = document.createElement('div');
            speakerDiv.classList.add('sub-speaker-select-area');
            speakerDiv.style.width = '115px';
            speakerDiv.style.flexShrink = '0';
            speakerDiv.style.display = 'flex';
            speakerDiv.style.flexDirection = 'column';
            speakerDiv.style.gap = '4px';

            const spkSelect = document.createElement('select');
            spkSelect.classList.add('sub-time-input', 'speaker-select-input');
            spkSelect.style.width = '115px';
            spkSelect.style.padding = '5px 8px';
            spkSelect.style.borderRadius = '6px';
            spkSelect.style.background = 'rgba(255, 255, 255, 0.05)';
            spkSelect.style.color = 'var(--text-primary)';
            spkSelect.style.border = '1px solid var(--border-color)';
            spkSelect.style.fontSize = '0.75rem';
            spkSelect.style.cursor = 'pointer';

            const currentSpeaker = sub.speaker || 'Speaker A';
            const standardSpeakers = ['Speaker A', 'Speaker B', 'Speaker C', 'Speaker D'];
            let allSpeakers = [...standardSpeakers];
            if (currentSpeaker && !standardSpeakers.includes(currentSpeaker)) {
                allSpeakers.push(currentSpeaker);
            }

            allSpeakers.forEach(spk => {
                const opt = document.createElement('option');
                opt.value = spk;
                let displayName = spk;
                if (spk === 'Speaker A') displayName = 'Giọng A (Nữ/Trung)';
                else if (spk === 'Speaker B') displayName = 'Giọng B (Nam)';
                else if (spk === 'Speaker C') displayName = 'Giọng C';
                else if (spk === 'Speaker D') displayName = 'Giọng D';
                
                opt.textContent = displayName;
                opt.style.background = '#1e1e24';
                if (currentSpeaker === spk) {
                    opt.selected = true;
                }
                spkSelect.appendChild(opt);
            });

            speakerDiv.appendChild(spkSelect);

            row.appendChild(timeDiv);
            row.appendChild(textDiv);
            row.appendChild(speakerDiv);

            row.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

                subtitleList.querySelectorAll('.subtitle-item-row').forEach(r => r.classList.remove('active'));
                row.classList.add('active');

                const startTime = parseFloat(startInput.value);
                if (!isNaN(startTime)) {
                    reviewVideoPlayer.currentTime = startTime;
                    reviewVideoPlayer.play().catch(() => {});
                }
            });

            const triggerPause = () => {
                pauseCountdown();
            };
            startInput.addEventListener('input', triggerPause);
            endInput.addEventListener('input', triggerPause);
            transInput.addEventListener('input', triggerPause);
            spkSelect.addEventListener('change', triggerPause);

            subtitleList.appendChild(row);
        });
    }

    function updateCountdownUI(seconds, isPaused) {
        if (isPaused) {
            reviewCountdownContainer.classList.add('paused');
            subtitleCountdownText.textContent = '⏸ Đã tạm dừng đếm ngược (đang chỉnh sửa...)';
        } else {
            reviewCountdownContainer.classList.remove('paused');
            subtitleCountdownText.textContent = `Tự động tiếp tục sau: ${seconds}s`;
        }
    }

    async function pauseCountdown() {
        if (reviewCountdownContainer.classList.contains('paused')) return;

        if (countdownInterval) {
            clearInterval(countdownInterval);
            countdownInterval = null;
        }
        updateCountdownUI(0, true);

        try {
            await fetch(`/api/translate/review/pause/${currentJobId}`, { method: 'POST' });
            appendLogLine('Đã tạm dừng đếm ngược để sửa phụ đề.', 'info');
        } catch (e) {
            console.error('Không thể tạm dừng đếm ngược ở máy chủ:', e);
        }
    }

    function gatherSubtitlesData() {
        const rows = subtitleList.querySelectorAll('.subtitle-item-row');
        const updatedSubs = [];

        rows.forEach(row => {
            const index = parseInt(row.dataset.index);
            const startVal = parseFloat(row.querySelector('.start-time-input').value);
            const endVal = parseFloat(row.querySelector('.end-time-input').value);
            const translationVal = row.querySelector('.translation-text-input').value;
            const speakerVal = row.querySelector('.speaker-select-input').value;

            const originalSub = reviewSubtitles[index];
            updatedSubs.push({
                text: originalSub.text,
                translation: translationVal,
                start: startVal,
                end: endVal,
                speaker: speakerVal
            });
        });

        return updatedSubs;
    }

    async function submitRevisedSubtitles(subtitles) {
        if (countdownInterval) clearInterval(countdownInterval);
        subtitleReviewModal.classList.add('hidden');
        reviewVideoPlayer.pause();

        appendLogLine('Đang lưu phụ đề chỉnh sửa và tiếp tục lồng tiếng...', 'info');

        try {
            const response = await fetch(`/api/translate/review/continue/${currentJobId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subtitles: subtitles })
            });

            if (!response.ok) {
                throw new Error('Lỗi lưu phụ đề từ máy chủ.');
            }

            appendLogLine('Lưu phụ đề thành công. Hệ thống tiếp tục quy trình lồng tiếng AI.', 'success');

            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => pollJobStatus(currentJobId), 1200);

        } catch (err) {
            appendLogLine(`Lỗi khi tiếp tục: ${err.message}`, 'error');
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => pollJobStatus(currentJobId), 1200);
        }
    }

    function autoSubmitSubtitles() {
        const subs = gatherSubtitlesData();
        submitRevisedSubtitles(subs);
    }

    btnEditSubtitles.addEventListener('click', () => {
        pauseCountdown();
    });

    btnContinueTTS.addEventListener('click', () => {
        const subs = gatherSubtitlesData();
        submitRevisedSubtitles(subs);
    });

    // ─── Glossary Editor Modal (Popup) ──────────────────────────────────
    const glossaryModal = document.getElementById('glossaryModal');
    const btnOpenGlossaryModal = document.getElementById('btnOpenGlossaryModal');
    const btnCloseGlossary = document.getElementById('btnCloseGlossary');
    const btnSaveGlossary = document.getElementById('btnSaveGlossary');
    const glossaryStyleSelect = document.getElementById('glossaryStyleSelect');
    const glossaryTextarea = document.getElementById('glossaryTextarea');
    const glossaryOverlay = document.getElementById('glossaryOverlay');

    async function loadGlossary(style) {
        glossaryTextarea.value = 'Đang tải từ điển...';
        try {
            const resp = await fetch(`/api/glossary/${style}`);
            if (!resp.ok) throw new Error('Không thể tải từ điển.');
            const data = await resp.json();
            glossaryTextarea.value = data.content || '';
        } catch (err) {
            glossaryTextarea.value = `Lỗi: ${err.message}`;
        }
    }

    if (btnOpenGlossaryModal) {
        btnOpenGlossaryModal.addEventListener('click', () => {
            glossaryModal.classList.remove('hidden');
            // Mặc định chọn từ điển tương ứng với style hiện tại của form nếu có
            const currentStyle = document.querySelector('.translate-toggle-btn.active')?.dataset.style || 'default';
            if (currentStyle && glossaryStyleSelect) {
                glossaryStyleSelect.value = currentStyle;
            }
            loadGlossary(glossaryStyleSelect.value || 'default');
        });
    }

    if (glossaryStyleSelect) {
        glossaryStyleSelect.addEventListener('change', (e) => {
            loadGlossary(e.target.value);
        });
    }

    if (btnCloseGlossary) {
        btnCloseGlossary.addEventListener('click', () => {
            glossaryModal.classList.add('hidden');
        });
    }
    if (glossaryOverlay) {
        glossaryOverlay.addEventListener('click', () => {
            glossaryModal.classList.add('hidden');
        });
    }

    if (btnSaveGlossary) {
        btnSaveGlossary.addEventListener('click', async () => {
            const style = glossaryStyleSelect.value;
            const content = glossaryTextarea.value;
            btnSaveGlossary.disabled = true;
            btnSaveGlossary.querySelector('span').textContent = '⏳ Đang lưu...';
            
            try {
                const resp = await fetch(`/api/glossary/${style}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content })
                });
                if (!resp.ok) throw new Error('Không thể lưu từ điển.');
                const data = await resp.json();
                appendLogLine(`[TỪ ĐIỂN] ${data.message}`, 'success');
                alert(data.message);
                glossaryModal.classList.add('hidden');
            } catch (err) {
                alert(`Lỗi: ${err.message}`);
                appendLogLine(`[TỪ ĐIỂN LỖI] ${err.message}`, 'error');
            } finally {
                btnSaveGlossary.disabled = false;
                btnSaveGlossary.querySelector('span').textContent = 'Lưu Từ điển';
            }
        });
    }

    // --- Background scan resolutions when URL changes ---
    const resolutionSelect = document.getElementById('videoResolution');
    const resolutionScanStatus = document.getElementById('resolutionScanStatus');
    let lastScannedUrl = '';
    let scanTimeout = null;

    async function scanUrlResolutions(url) {
        if (!url || !url.startsWith('http')) return;
        if (url === lastScannedUrl) return;
        
        lastScannedUrl = url;
        if (resolutionScanStatus) resolutionScanStatus.style.display = 'inline';
        
        try {
            const resp = await fetch(`/api/video/info?url=${encodeURIComponent(url)}`);
            if (!resp.ok) throw new Error('Quét lỗi');
            const data = await resp.json();
            
            if (data.status === 'success' && data.resolutions && data.resolutions.length > 0) {
                if (resolutionSelect) {
                    resolutionSelect.innerHTML = '';
                    data.resolutions.forEach(res => {
                        const opt = document.createElement('option');
                        opt.value = res.value;
                        opt.textContent = res.label;
                        if (res.value === '1080') {
                            opt.selected = true;
                        }
                        resolutionSelect.appendChild(opt);
                    });
                    
                    if (!resolutionSelect.querySelector('option[selected]')) {
                        resolutionSelect.selectedIndex = 0;
                    }
                }
                appendLogLine(`[ĐỘ PHÂN GIẢI] Đã tự động tải các độ phân giải khả dụng cho: "${data.title}"`, 'success');
            }
        } catch (err) {
            console.warn('Không quét được độ phân giải khả dụng:', err);
        } finally {
            if (resolutionScanStatus) resolutionScanStatus.style.display = 'none';
        }
    }

    if (videoUrlInput) {
        videoUrlInput.addEventListener('input', () => {
            if (scanTimeout) clearTimeout(scanTimeout);
            scanTimeout = setTimeout(() => {
                scanUrlResolutions(videoUrlInput.value.trim());
            }, 1000);
        });

        videoUrlInput.addEventListener('paste', () => {
            setTimeout(() => {
                scanUrlResolutions(videoUrlInput.value.trim());
            }, 150);
        });
    }
});
