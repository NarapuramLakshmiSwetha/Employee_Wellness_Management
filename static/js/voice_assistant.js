// AI Voice Assistant for Employee Wellness Platform
// Leverages Web Speech API (SpeechSynthesis) to read and explain page contents.

(function() {
    if (!('speechSynthesis' in window)) {
        console.warn('Speech Synthesis API is not supported in this browser.');
        return;
    }

    // Identify page type
    let pageType = '';
    if (document.getElementById('form-health-data')) {
        pageType = 'health_data';
    } else if (document.getElementById('wellnessChart')) {
        pageType = 'risk_prediction';
    } else if (document.querySelector('.recommendation-grid')) {
        pageType = 'recommendations';
    } else if (document.getElementById('sentiment-form')) {
        pageType = 'sentiment_analytics';
    } else if (document.getElementById('health-factors-list') || document.getElementById('wellness-score-card')) {
        pageType = 'wellness_performance';
    }

    if (!pageType) return;

    // Inject CSS styling
    const style = document.createElement('style');
    style.textContent = `
        .voice-assistant-wrapper {
            margin-left: auto;
        }
        .voice-ctrl-btn {
            background: none;
            border: none;
            color: #ffffff;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 8px 14px;
            border-radius: 8px;
            transition: all 0.2s ease;
        }
        .voice-ctrl-btn:hover {
            background: rgba(255, 255, 255, 0.08) !important;
            color: var(--secondary) !important;
            transform: translateY(-1px);
        }
        #voice-btn-stop:hover {
            background: rgba(239, 68, 68, 0.15) !important;
            color: #ef4444 !important;
        }
        .voice-highlight {
            border-color: var(--secondary) !important;
            box-shadow: 0 0 20px rgba(6, 182, 212, 0.4) !important;
            transition: all 0.4s ease;
            position: relative;
            z-index: 10;
        }
        @keyframes voice-indicator-pulse {
            0% { transform: scale(1); opacity: 0.6; }
            50% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(1); opacity: 0.6; }
        }
        .voice-indicator-dot {
            animation: voice-indicator-pulse 1.5s infinite ease-in-out;
        }
    `;
    document.head.appendChild(style);

    // Initialize Voice list
    let selectedVoice = null;
    function loadVoice() {
        const voices = window.speechSynthesis.getVoices();
        selectedVoice = voices.find(v => v.lang.includes('en-US') && v.name.includes('Google')) ||
                        voices.find(v => v.lang.includes('en') && v.name.includes('Natural')) ||
                        voices.find(v => v.lang.includes('en-US')) ||
                        voices.find(v => v.lang.startsWith('en')) ||
                        voices[0];
    }
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
        window.speechSynthesis.onvoiceschanged = loadVoice;
    }
    loadVoice();

    // Voice assistant controller
    window.voiceAssistant = {
        speechParts: [],
        currentIndex: -1,
        isPaused: false,
        isPlaying: false,

        // Generate parts for Health Data form
        getHealthDataParts: function() {
            const parts = [];
            parts.push({
                text: "Hello! I am your AI health assistant. Let's review your recorded health profile details.",
                selector: "h2"
            });

            const empId = document.querySelector('#card-employee-info input[value]')?.value || '';
            const username = document.querySelector('#card-employee-info input:nth-of-type(2)')?.value || '';
            let empText = "For basic employee information. ";
            if (username) empText += `Your username is ${username}. `;
            if (empId) empText += `Your employee identity is ${empId}. `;
            parts.push({ text: empText, selector: "#card-employee-info" });

            const bloodGroup = document.getElementById('blood-group')?.value || '';
            const height = document.getElementById('height')?.value || '';
            const weight = document.getElementById('weight')?.value || '';
            const bmi = document.getElementById('bmi-value')?.textContent || '';
            const bmiCat = document.getElementById('bmi-category')?.textContent || '';
            const bp = document.getElementById('blood-pressure')?.value || '';
            const water = document.getElementById('water-intake')?.value || '';

            let basicText = "First section: Basic Health Details. ";
            if (bloodGroup) basicText += `Your blood group is ${bloodGroup}. `;
            if (height) basicText += `Your height is ${height} centimeters. `;
            if (weight) basicText += `Your weight is ${weight} kilograms. `;
            if (bmi && bmi !== '--') {
                basicText += `Your Body Mass Index, or B.M.I., is ${bmi}, which is in the ${bmiCat} range. Body Mass Index calculates body fat based on height and weight. `;
            }
            if (bp) {
                const [sys, dia] = bp.split('/');
                basicText += `Your blood pressure is ${sys} over ${dia} millimeters of mercury. Normal blood pressure is typically under one hundred and twenty over eighty. `;
            }
            if (water) {
                basicText += `Your daily water intake is ${water}. Proper hydration supports blood pressure regulation and overall cell wellness. `;
            }
            parts.push({ text: basicText, selector: "#card-basic-health" });

            const lastCheckup = document.getElementById('last-checkup')?.value || '';
            const nextCheckup = document.getElementById('next-checkup')?.value || '';
            const healthStatus = document.getElementById('health-status')?.value || '';

            let checkupText = "Second section: Health Check-up History. ";
            if (healthStatus) checkupText += `Your general health rating is ${healthStatus}. `;
            if (lastCheckup) checkupText += `Your last checkup date was ${lastCheckup}. `;
            if (nextCheckup) checkupText += `Your next screening is due on ${nextCheckup}. Regular clinical assessments are essential for prevention. `;
            parts.push({ text: checkupText, selector: "#card-health-checkup" });

            const allergiesRadio = document.querySelector('input[name="has_allergies"]:checked')?.value || 'No';
            const allergiesDetail = document.getElementById('allergies-detail')?.value || '';
            const medicalCondition = document.getElementById('medical-condition')?.value || 'None';
            const conditionOther = document.getElementById('condition-other')?.value || '';
            const disabilityRadio = document.querySelector('input[name="has_disability"]:checked')?.value || 'No';
            const disabilityDetail = document.getElementById('disability-detail')?.value || '';
            const medication = document.getElementById('current-medication')?.value || '';

            let medText = "Third section: Medical Information. ";
            if (allergiesRadio === 'Yes' && allergiesDetail) {
                medText += `You have registered allergies to ${allergiesDetail}. `;
            } else {
                medText += "You have no reported allergies. ";
            }
            if (medicalCondition === 'Other' && conditionOther) {
                medText += `Your listed medical condition is ${conditionOther}. `;
            } else if (medicalCondition && medicalCondition !== 'None') {
                medText += `Your listed medical condition is ${medicalCondition}. `;
            } else {
                medText += "You have no active chronic medical conditions listed. ";
            }
            if (disabilityRadio === 'Yes' && disabilityDetail) {
                medText += `Disability status is listed with details: ${disabilityDetail}. `;
            }
            if (medication) {
                medText += `Your current prescribed medication details are: ${medication}. `;
            }
            parts.push({ text: medText, selector: "#card-medical-info" });

            const smoking = document.getElementById('smoking-habit')?.value || '';
            const alcohol = document.getElementById('alcohol-consumption')?.value || '';
            const sugar = document.getElementById('sugar-level')?.value || '';
            const exerciseFreq = document.getElementById('exercise-frequency')?.value || '';
            const exerciseType = document.getElementById('exercise-type')?.value || '';
            const steps = document.getElementById('daily-step-count')?.value || '';
            const stress = document.getElementById('stress-level')?.value || '';
            const attendance = document.getElementById('attendance-percentage')?.value || '';
            const workHours = document.getElementById('work-hours')?.value || '';
            const remarks = document.getElementById('doctor-remarks')?.value || '';

            let lifeText = "Fourth section: Lifestyle and Work Data. ";
            if (smoking) lifeText += `Smoking habit is ${smoking}. `;
            if (alcohol) lifeText += `Alcohol consumption is ${alcohol}. `;
            if (sugar) lifeText += `Blood sugar level is evaluated as ${sugar}. `;
            if (exerciseFreq && exerciseFreq !== 'Never') {
                lifeText += `You exercise ${exerciseFreq} using ${exerciseType || 'active routines'}. `;
            } else {
                lifeText += "You do not engage in regular exercise. ";
            }
            if (steps) lifeText += `Your daily step count averages ${steps} steps. `;
            if (stress) lifeText += `Your stress level is ${stress}. High stress can release cortisol, affecting blood pressure and sleep quality. `;
            if (workHours) lifeText += `You work ${workHours} hours per day. `;
            if (attendance) lifeText += `Your office attendance is ${attendance} percent. `;
            if (remarks) lifeText += `Doctor remarks note: ${remarks}. `;
            parts.push({ text: lifeText, selector: "#card-lifestyle" });

            parts.push({
                text: "This completes your health data summary. Make sure to keep your details up to date.",
                selector: ".action-footer"
            });

            return parts;
        },

        // Generate parts for Risk Prediction
        getRiskPredictionParts: function() {
            const parts = [];
            parts.push({
                text: "Hello! Let's review your AI Wellness Risk Prediction analysis.",
                selector: "h2"
            });

            const scoreVal = document.getElementById('gauge-val')?.textContent || '';
            const riskBadge = document.querySelector('.risk-badge-large')?.textContent.trim() || 'Unknown Risk';
            let riskText = `Your overall wellness rating is scored at ${scoreVal} out of one hundred. Based on this, your predicted profile is classified as ${riskBadge}. `;
            parts.push({ text: riskText, selector: ".prediction-card:nth-of-type(1)" });

            const aiSummary = document.querySelector('.ai-narrative-box p')?.textContent.trim() || '';
            if (aiSummary) {
                parts.push({
                    text: `Here is the details of the AI narrative analysis: ${aiSummary}`,
                    selector: ".ai-narrative-box"
                });
            }

            let detailsText = "Let's review the main health risk factors contributing to this prediction. ";
            const metrics = document.querySelectorAll('.metric-row');
            metrics.forEach(row => {
                const title = row.querySelector('.metric-title')?.textContent.trim() || '';
                const val = row.querySelector('.metric-value')?.textContent.trim() || '';
                detailsText += `For ${title}, your score is rated at ${val}. `;
            });
            parts.push({ text: detailsText, selector: ".prediction-card:nth-of-type(2)" });

            parts.push({
                text: "Please look at your personalized recommendations to learn how to mitigate these risks and improve your wellness scores.",
                selector: ".btn-action"
            });

            return parts;
        },

        // Generate parts for Personalized Recommendations
        getRecommendationsParts: function() {
            const parts = [];
            const riskProfile = document.querySelector('.badge-status')?.textContent.trim() || 'Unknown';
            parts.push({
                text: `Hello! Let's go over your personalized wellness recommendations. Your overall risk profile is classified as ${riskProfile}.`,
                selector: "h2"
            });

            const cards = document.querySelectorAll('.rec-card');
            if (cards.length > 0) {
                cards.forEach((card, index) => {
                    const title = card.querySelector('.rec-title')?.textContent.trim() || '';
                    const desc = card.querySelector('.rec-desc')?.textContent.trim() || '';
                    const benefit = card.querySelector('.rec-benefit-text')?.textContent.trim() || '';
                    const priority = card.querySelector('.priority-tag')?.textContent.trim() || '';
                    
                    let cardText = `Recommendation ${index + 1}: ${title}. Priority: ${priority}. `;
                    cardText += `Description: ${desc} `;
                    cardText += `Expected wellness benefit: ${benefit}.`;
                    
                    parts.push({ text: cardText, selector: card });
                });
            } else {
                parts.push({
                    text: "You currently have no critical recommendations. Your wellness scores are fully balanced. Continue maintaining healthy habits!",
                    selector: ".glass-card"
                });
            }

            parts.push({
                text: "You can save this plan to your profile or download the P.D.F. health report using the buttons at the bottom.",
                selector: ".btn-action"
            });

            return parts;
        },

        // Generate parts for Sentiment Analytics
        getSentimentAnalyticsParts: function() {
            const parts = [];
            parts.push({
                text: "Hello! Welcome to your Mental Health and Sentiment Analytics portal. Share your weekly thoughts or feedback to evaluate your emotional wellness.",
                selector: "h2"
            });

            parts.push({
                text: "You can type your weekly wellness journal entries in the submission form below. Our VADER analyzer detects sentiment trends and stress levels.",
                selector: "#sentiment-form"
            });

            const resultsCard = document.querySelector('#result-card');
            if (resultsCard && resultsCard.style.display !== 'none') {
                const sentiment = document.getElementById('res-sentiment')?.textContent || '';
                const mentalStatus = document.getElementById('res-status')?.textContent || '';
                const riskLevel = document.getElementById('res-risk')?.textContent || '';
                const score = document.getElementById('res-score')?.textContent || '';
                
                let resText = `Analysis output: Your sentiment is classified as ${sentiment}. Your mental health status is ${mentalStatus}, with a ${riskLevel} risk level and compound polarity score of ${score}. `;
                parts.push({ text: resText, selector: '#result-card' });

                const recs = document.getElementById('res-recommendations')?.textContent || '';
                if (recs) {
                    parts.push({
                        text: `Tailored support recommendation: ${recs}`,
                        selector: '#res-recommendations'
                    });
                }
            }

            const historyTbody = document.getElementById('history-tbody');
            if (historyTbody && !historyTbody.querySelector('#history-empty-row')) {
                const rows = historyTbody.querySelectorAll('tr');
                if (rows.length > 0) {
                    parts.push({
                        text: `You have ${rows.length} journal logs recorded in your historical sentiment log table.`,
                        selector: '#history-tbody'
                    });
                }
            }

            return parts;
        },

        // Generate parts for Wellness Performance
        getWellnessPerformanceParts: function() {
            const parts = [];
            parts.push({
                text: "Welcome to your Wellness Performance Dashboard. Here you can review your personal health score, key performance indicators, and tailored improvement insights.",
                selector: ".wpd-hero"
            });

            const tiles = document.querySelectorAll('.kpi-tile');
            if (tiles.length > 0) {
                let kpiText = "Key Performance Indicators summary: ";
                tiles.forEach(tile => {
                    const label = tile.querySelector('div:first-child')?.textContent.trim() || '';
                    const val = tile.querySelector('h3')?.textContent.trim() || '';
                    if (label && val) {
                        kpiText += `${label} is ${val}. `;
                    }
                });
                parts.push({ text: kpiText, selector: '#kpi-grid' });
            }

            const score = document.getElementById('health-score-val')?.textContent || '';
            const status = document.getElementById('health-score-badge-text')?.textContent || '';
            const interp = document.getElementById('health-score-interpretation')?.textContent || '';

            if (score) {
                let scoreText = `Your overall personal health score is ${score} out of one hundred, rated as ${status}. `;
                if (interp) {
                    scoreText += `Analysis note: ${interp}`;
                }
                parts.push({ text: scoreText, selector: '#wellness-score-card' });
            }

            const factors = document.querySelectorAll('.factor-item');
            if (factors.length > 0) {
                let factorText = "Health Factor Score Breakdown: ";
                factors.forEach(item => {
                    const name = item.querySelector('.factor-name')?.textContent.trim() || '';
                    const val = item.querySelector('.factor-value')?.textContent.trim() || '';
                    const pts = item.querySelector('.factor-pts')?.textContent.trim() || '';
                    if (name && pts) {
                        factorText += `${name}: ${val}, scoring ${pts}. `;
                    }
                });
                parts.push({ text: factorText, selector: '#health-factors-list' });
            }

            return parts;
        },

        // Start speaking sequence
        startSpeech: function() {
            window.speechSynthesis.cancel();
            document.querySelectorAll('.voice-highlight').forEach(el => el.classList.remove('voice-highlight'));
            
            // Gather correct parts
            if (pageType === 'health_data') {
                this.speechParts = this.getHealthDataParts();
            } else if (pageType === 'risk_prediction') {
                this.speechParts = this.getRiskPredictionParts();
            } else if (pageType === 'recommendations') {
                this.speechParts = this.getRecommendationsParts();
            } else if (pageType === 'sentiment_analytics') {
                this.speechParts = this.getSentimentAnalyticsParts();
            } else if (pageType === 'wellness_performance') {
                this.speechParts = this.getWellnessPerformanceParts();
            }

            if (this.speechParts.length === 0) return;

            this.currentIndex = 0;
            this.isPlaying = true;
            this.isPaused = false;

            // Toggle play/pause UI
            document.getElementById('voice-btn-listen').style.display = 'none';
            document.getElementById('voice-playback-controls').style.display = 'flex';
            document.getElementById('voice-btn-pause').style.display = 'flex';
            document.getElementById('voice-btn-play').style.display = 'none';

            this.speakNext();
        },

        // Speak the current index part
        speakNext: function() {
            if (!this.isPlaying || this.currentIndex >= this.speechParts.length) {
                this.stopSpeech();
                return;
            }

            const part = this.speechParts[this.currentIndex];
            const utterance = new SpeechSynthesisUtterance(part.text);
            if (selectedVoice) {
                utterance.voice = selectedVoice;
            }
            utterance.rate = 1.0;
            utterance.pitch = 1.0;

            utterance.onstart = () => {
                // Remove highlight from all elements
                document.querySelectorAll('.voice-highlight').forEach(el => el.classList.remove('voice-highlight'));
                
                // Add highlight to current element
                if (part.selector) {
                    const el = document.querySelector(part.selector);
                    if (el) {
                        el.classList.add('voice-highlight');
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            };

            utterance.onend = () => {
                if (this.isPlaying && !this.isPaused) {
                    this.currentIndex++;
                    this.speakNext();
                }
            };

            utterance.onerror = (e) => {
                console.error('Speech synthesis error:', e);
                this.stopSpeech();
            };

            window.speechSynthesis.speak(utterance);
        },

        // Pause speech
        pauseSpeech: function() {
            window.speechSynthesis.pause();
            this.isPaused = true;
            document.getElementById('voice-btn-pause').style.display = 'none';
            document.getElementById('voice-btn-play').style.display = 'flex';
        },

        // Resume speech
        resumeSpeech: function() {
            window.speechSynthesis.resume();
            this.isPaused = false;
            document.getElementById('voice-btn-pause').style.display = 'flex';
            document.getElementById('voice-btn-play').style.display = 'none';
            
            // Fix Chrome/Safari bugs where resume sometimes fails or gets stuck
            if (!window.speechSynthesis.speaking) {
                this.speakNext();
            }
        },

        // Stop speaking completely
        stopSpeech: function() {
            window.speechSynthesis.cancel();
            this.isPlaying = false;
            this.isPaused = false;
            this.currentIndex = -1;

            // Remove all active highlights
            document.querySelectorAll('.voice-highlight').forEach(el => el.classList.remove('voice-highlight'));

            // Toggle play/pause UI back to main listen button
            document.getElementById('voice-btn-listen').style.display = 'flex';
            document.getElementById('voice-playback-controls').style.display = 'none';
        }
    };

    // Inject UI element on page load
    function injectVoiceControls() {
        const container = document.createElement('div');
        container.className = 'voice-assistant-wrapper';
        container.id = 'voice-assistant-container';
        container.innerHTML = `
            <div class="voice-assistant-controls glass-card" style="display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.08); background: rgba(15, 23, 42, 0.45); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); box-shadow: var(--shadow-premium);">
                <button id="voice-btn-listen" class="voice-ctrl-btn" style="color: #ffffff;" onclick="voiceAssistant.startSpeech()">
                    <i class="fas fa-volume-high" style="color: var(--secondary);"></i>
                    <span>🔊 Listen</span>
                </button>
                
                <div id="voice-playback-controls" style="display: none; align-items: center; gap: 6px;">
                    <span style="font-size: 11px; color: var(--text-secondary); margin-right: 4px; display: flex; align-items: center; gap: 4px;">
                        <span class="voice-indicator-dot" style="width: 8px; height: 8px; border-radius: 50%; background: #06b6d4; display: inline-block;"></span>
                        AI Voice
                    </span>
                    <div style="width: 1px; height: 16px; background: rgba(255,255,255,0.15); margin: 0 4px;"></div>
                    <button id="voice-btn-play" class="voice-ctrl-btn" onclick="voiceAssistant.resumeSpeech()" style="display: none; padding: 6px;" title="Play">
                        <i class="fas fa-play"></i>
                    </button>
                    <button id="voice-btn-pause" class="voice-ctrl-btn" onclick="voiceAssistant.pauseSpeech()" style="padding: 6px;" title="Pause">
                        <i class="fas fa-pause"></i>
                    </button>
                    <button id="voice-btn-stop" class="voice-ctrl-btn" onclick="voiceAssistant.stopSpeech()" style="padding: 6px;" title="Stop">
                        <i class="fas fa-stop"></i>
                    </button>
                </div>
            </div>
        `;
        
        // Find position
        let titleDiv = document.querySelector('.dashboard-wrapper > div[style*="margin-bottom: 40px"]');
        if (!titleDiv) {
            titleDiv = document.querySelector('.dashboard-wrapper > div[style*="margin-bottom: 10px"]');
        }
        if (!titleDiv) {
            titleDiv = document.querySelector('.dashboard-wrapper > div[style*="margin-bottom:10px"]');
        }
        if (!titleDiv) {
            titleDiv = document.querySelector('.dashboard-wrapper > div');
        }

        if (titleDiv) {
            titleDiv.style.display = 'flex';
            titleDiv.style.justifyContent = 'space-between';
            titleDiv.style.alignItems = 'flex-end';
            titleDiv.style.flexWrap = 'wrap';
            titleDiv.style.gap = '20px';
            titleDiv.appendChild(container);
        }
    }

    // Auto run on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectVoiceControls);
    } else {
        injectVoiceControls();
    }

    // Make sure we stop speech on page navigation/unload
    window.addEventListener('beforeunload', () => {
        window.speechSynthesis.cancel();
    });
})();
