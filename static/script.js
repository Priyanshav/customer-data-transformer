document.addEventListener('DOMContentLoaded', () => {
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            e.target.classList.add('active');
            document.getElementById(`${e.target.dataset.tab}-config`).classList.add('active');
        });
    });

    // Default JSON Config
    const defaultJsonConfig = {
        fields: [
            { path: "candidate_id", type: "string", required: true },
            { path: "full_name", type: "string", required: true },
            { path: "emails", type: "string[]" },
            { path: "phones", type: "string[]" },
            { path: "location", type: "object" },
            { path: "skills", type: "object[]" },
            { path: "experience", type: "object[]" },
            { path: "education", type: "object[]" },
            { path: "years_experience", type: "number" }
        ],
        include_confidence: true,
        on_missing: "null"
    };

    const rawConfigEl = document.getElementById('raw-config');
    rawConfigEl.value = JSON.stringify(defaultJsonConfig, null, 2);

    document.getElementById('reset-config').addEventListener('click', () => {
        rawConfigEl.value = JSON.stringify(defaultJsonConfig, null, 2);
    });

    // File Upload Handling
    const fileInput = document.getElementById('file-input');
    const fileList = document.getElementById('file-list');
    let selectedFiles = [];

    fileInput.addEventListener('change', (e) => {
        selectedFiles = Array.from(e.target.files);
        updateFileList();
    });

    function updateFileList() {
        fileList.innerHTML = '';
        selectedFiles.forEach(file => {
            const li = document.createElement('li');
            li.textContent = file.name;
            fileList.appendChild(li);
        });
    }

    // Drag and Drop
    const dropZone = document.getElementById('drop-zone');
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            selectedFiles = Array.from(e.dataTransfer.files);
            fileInput.files = e.dataTransfer.files;
            updateFileList();
        }
    });

    // Form Submission
    const errorMsg = document.getElementById('error-message');
    const resultsSection = document.getElementById('results-section');
    const profilesContainer = document.getElementById('profiles-container');
    const rawJsonOutput = document.getElementById('raw-json-output');
    let lastResult = null;

    document.getElementById('transform-btn').addEventListener('click', async () => {
        if (selectedFiles.length === 0) {
            showError("Please upload at least one file.");
            return;
        }
        
        hideError();
        document.getElementById('transform-btn').textContent = "Processing...";
        document.getElementById('transform-btn').disabled = true;

        const formData = new FormData();
        selectedFiles.forEach(file => formData.append('files', file));

        // Determine which config to send
        const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
        if (activeTab === 'advanced') {
            try {
                JSON.parse(rawConfigEl.value); // validate
                formData.append('config', rawConfigEl.value);
            } catch (e) {
                showError("Invalid JSON in advanced config.");
                resetBtn();
                return;
            }
        } else {
            const dynamicConfig = JSON.parse(JSON.stringify(defaultJsonConfig));
            dynamicConfig.include_confidence = document.getElementById('inc_confidence').checked;
            dynamicConfig.on_missing = document.getElementById('on_missing').value;
            formData.append('config', JSON.stringify(dynamicConfig));
        }

        try {
            const response = await fetch('/api/transform', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || "Transformation failed.");
            }

            lastResult = data;
            renderResults(data);
            
        } catch (err) {
            showError(err.message);
        } finally {
            resetBtn();
        }
    });

    function resetBtn() {
        document.getElementById('transform-btn').textContent = "Transform Data";
        document.getElementById('transform-btn').disabled = false;
    }

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.classList.remove('hidden');
        resultsSection.classList.add('hidden');
    }
    
    function hideError() {
        errorMsg.classList.add('hidden');
    }

    function getConfidenceClass(conf) {
        if (!conf) return 'conf-med';
        if (conf >= 0.9) return 'conf-high';
        if (conf >= 0.7) return 'conf-med';
        return 'conf-low';
    }

    function renderResults(profiles) {
        resultsSection.classList.remove('hidden');
        rawJsonOutput.textContent = JSON.stringify(profiles, null, 2);
        profilesContainer.innerHTML = '';

        profiles.forEach(profile => {
            const card = document.createElement('div');
            card.className = 'profile-card';

            if (profile.error) {
                card.innerHTML = `<h3 style="color:var(--error)">Error for candidate ${profile.candidate_id}</h3><p>${profile.error}</p>`;
                profilesContainer.appendChild(card);
                return;
            }

            const header = document.createElement('div');
            header.className = 'profile-header';
            
            let confBadge = '';
            if (profile.overall_confidence !== undefined) {
                const confCls = getConfidenceClass(profile.overall_confidence);
                confBadge = `<span class="confidence-badge ${confCls}">Overall Conf: ${(profile.overall_confidence * 100).toFixed(0)}%</span>`;
            }
            
            header.innerHTML = `<h3>${profile.full_name || 'Unknown Name'} ${confBadge}</h3>`;
            card.appendChild(header);

            // Create lookup map for provenance
            const provMap = {};
            if (profile.provenance) {
                profile.provenance.forEach(p => {
                    if (!provMap[p.field]) provMap[p.field] = [];
                    provMap[p.field].push(`${p.source} (${p.method})`);
                });
            }

            const renderField = (label, value, key) => {
                if (value == null) return '';
                
                let provHtml = '';
                if (provMap[key]) {
                    const sources = provMap[key].join(', ');
                    provHtml = `<span class="prov-badge" title="Source: ${sources}">ℹ️</span>`;
                }

                let valHtml = '';
                if (Array.isArray(value)) {
                    if (value.length === 0) return '';
                    if (typeof value[0] === 'object') {
                        valHtml = value.map(v => JSON.stringify(v)).join('<br>');
                    } else {
                        valHtml = value.join(', ');
                    }
                } else if (typeof value === 'object') {
                    valHtml = JSON.stringify(value);
                } else {
                    valHtml = value;
                }

                return `
                    <div class="field-group">
                        <div class="field-label">${label}:</div>
                        <div class="field-value">${valHtml}</div>
                        ${provHtml}
                    </div>
                `;
            };

            const body = document.createElement('div');
            let bodyHtml = '';
            
            bodyHtml += renderField('Emails', profile.emails || profile.primary_email, 'email');
            bodyHtml += renderField('Phones', profile.phones || profile.phone, 'phone');
            bodyHtml += renderField('Location', profile.location, 'location');
            bodyHtml += renderField('Years Exp.', profile.years_experience, 'years_experience');
            
            if (profile.skills && profile.skills.length > 0) {
                 bodyHtml += renderField('Skills', profile.skills.map(s => typeof s === 'object' ? `${s.name} (${Math.round(s.confidence*100)}%)` : s), 'skill');
            }

            if (profile.experience && profile.experience.length > 0) {
                 const exps = profile.experience.map(e => {
                     let dateStr = "";
                     if (e.start && e.end) {
                         dateStr = ` (${e.start} - ${e.end})`;
                     } else if (e.start && !e.end) {
                         dateStr = ` (${e.start} - present)`;
                     } else if (!e.start && e.end) {
                         dateStr = ` (? - ${e.end})`;
                     }
                     
                     if (e.title && e.company) {
                         return `${e.title} @ ${e.company}${dateStr}`;
                     } else if (e.title) {
                         return `${e.title}${dateStr}`;
                     } else {
                         return `${e.company}${dateStr}`;
                     }
                 });
                 bodyHtml += renderField('Experience', exps, 'company'); // Simplification for tooltip mapping
            }

            if (profile.education && profile.education.length > 0) {
                 const edus = profile.education.map(e => {
                     let dateStr = "";
                     if (e.end_year) {
                         dateStr = ` (${e.end_year})`;
                     }
                     
                     if (e.degree && e.institution) {
                         return `${e.degree} @ ${e.institution}${dateStr}`;
                     } else if (e.degree) {
                         return `${e.degree}${dateStr}`;
                     } else {
                         return `${e.institution}${dateStr}`;
                     }
                 });
                 bodyHtml += renderField('Education', edus, 'edu_institution');
            }

            body.innerHTML = bodyHtml;
            card.appendChild(body);
            profilesContainer.appendChild(card);
        });
    }

    document.getElementById('download-btn').addEventListener('click', () => {
        if (!lastResult) return;
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(lastResult, null, 2));
        const anchor = document.createElement('a');
        anchor.setAttribute("href", dataStr);
        anchor.setAttribute("download", "canonical_profiles.json");
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    });
});
