/**
 * Health & Wellness Video Recommendations Engine
 * Provides curated YouTube health video dataset, profile auto-matching,
 * search filtering, and interactive card rendering with inline player embeds.
 */

const HEALTH_VIDEO_DATABASE = [
    // --- STRESS, YOGA & MEDITATION ---
    {
        id: "v7AYKMP6rOE",
        title: "Yoga For Complete Beginners - 20 Minute Home Yoga Workout",
        description: "A gentle, grounding yoga practice designed to release physical tension, quiet your mind, and relieve stress.",
        category: "Yoga",
        duration: "20 min",
        icon: "fa-spa",
        tags: ["stress", "yoga", "meditation", "anxiety", "mindfulness", "stretching"]
    },
    {
        id: "COp7BR_Dvps",
        title: "30 Minute Relaxing Yoga For Mental Health",
        description: "Slow seated flow to release deep physical tension, calm anxiety, and restore inner emotional balance.",
        category: "Yoga",
        duration: "30 min",
        icon: "fa-spa",
        tags: ["stress", "yoga", "meditation", "mental_health", "relaxation"]
    },
    {
        id: "inpok4MKVLM",
        title: "5-Minute Guided Meditation You Can Do Anywhere",
        description: "Quick 5-minute mindfulness session to lower cortisol, reset your focus, and eliminate acute work stress.",
        category: "Meditation",
        duration: "5 min",
        icon: "fa-om",
        tags: ["stress", "meditation", "mindfulness", "mental_health", "relaxation"]
    },
    {
        id: "ZToicYcHIOU",
        title: "Daily Calm | 10 Minute Mindfulness Meditation",
        description: "Guided mindfulness practice to reduce overthinking, ease panic, and foster daily peace of mind.",
        category: "Meditation",
        duration: "10 min",
        icon: "fa-brain",
        tags: ["stress", "meditation", "mindfulness", "anxiety", "mental_health"]
    },
    {
        id: "r7xsYgTeM2Q",
        title: "Sunrise Yoga | 15-Minute Morning Yoga Practice",
        description: "Energizing morning yoga routine to awaken muscles, improve flexibility, and start your day with focus.",
        category: "Yoga",
        duration: "15 min",
        icon: "fa-sun",
        tags: ["stress", "yoga", "stretching", "morning", "exercise"]
    },
    {
        id: "acUZdGd_3Dg",
        title: "Deep Breathing Exercises for Beginners",
        description: "Learn diaphragmatic and paced breathing techniques to lower heart rate and reduce stress levels.",
        category: "Breathing",
        duration: "8 min",
        icon: "fa-wind",
        tags: ["stress", "breathing", "meditation", "anxiety", "relaxation"]
    },
    {
        id: "hJbRpHZr_d0",
        title: "Yoga For Anxiety & Work Stress Relief",
        description: "Therapeutic yoga poses and breathing routines aimed at alleviating anxiety and body stiffness.",
        category: "Yoga",
        duration: "25 min",
        icon: "fa-heart-circle-check",
        tags: ["stress", "yoga", "anxiety", "mental_health", "blood_pressure"]
    },
    {
        id: "sTANio_2E0Q",
        title: "20 Min Full Body Stretch & Tension Relief",
        description: "Relaxing full body stretch routine ideal for relieving muscle tightness and promoting peaceful sleep.",
        category: "Stretching",
        duration: "20 min",
        icon: "fa-person-rays",
        tags: ["stress", "stretching", "exercise", "relaxation", "mobility"]
    },

    // --- WEIGHT LOSS, BMI, DIET & EXERCISE ---
    {
        id: "gC_L9qAHVJ8",
        title: "30-Minute Fat Burning Home Workout for Beginners",
        description: "High-energy, low-impact exercise routine for weight loss, stamina improvement, and lowering BMI.",
        category: "Weight Loss",
        duration: "30 min",
        icon: "fa-fire",
        tags: ["bmi", "weight_loss", "fat_burning", "exercise", "workout", "blood_sugar"]
    },
    {
        id: "ml6cT4AZdqI",
        title: "30-Minute HIIT Cardio Workout with Warm Up",
        description: "Cardio workout with no equipment needed, safe for burning calories and boosting cardiovascular health.",
        category: "Weight Loss",
        duration: "30 min",
        icon: "fa-person-running",
        tags: ["bmi", "weight_loss", "exercise", "workout", "cardio"]
    },
    {
        id: "UBMk30rjy0o",
        title: "20-Minute Full Body Workout - No Equipment",
        description: "Simple bodyweight workout designed to kickstart exercise frequency and build muscle endurance.",
        category: "Exercise",
        duration: "20 min",
        icon: "fa-dumbbell",
        tags: ["exercise", "workout", "beginner", "bmi", "weight_loss", "fitness"]
    },
    {
        id: "g_tea8ZNk5A",
        title: "15-Minute Full Body Stretch & Daily Mobility Routine",
        description: "Daily routine to awaken muscles, improve joint flexibility, and prevent posture strain from long work hours.",
        category: "Stretching",
        duration: "15 min",
        icon: "fa-child-reaching",
        tags: ["exercise", "stretching", "mobility", "beginner", "yoga"]
    },
    {
        id: "d3LPrhI0v-w",
        title: "5-Minute Movement & Activity Boost",
        description: "Quick 5-minute movement session to stay active, burn quick calories, and boost daily energy.",
        category: "Exercise",
        duration: "5 min",
        icon: "fa-bolt",
        tags: ["exercise", "walking", "beginner", "fitness", "bmi"]
    },

    // --- HYDRATION & HEALTH TIPS ---
    {
        id: "9iMGFqMmUFs",
        title: "What Would Happen If You Didn't Drink Water? (TED-Ed)",
        description: "Discover why staying hydrated improves brain focus, kidney function, digestion, and daily metabolic wellness.",
        category: "Hydration",
        duration: "5 min",
        icon: "fa-glass-water",
        tags: ["water", "hydration", "health_tips", "nutrition", "wellness"]
    },

    // --- BLOOD PRESSURE & DIABETES & HEART CARE ---
    {
        id: "s2NQhpFGIOg",
        title: "15 Min Paced Yoga & Breathing for Healthy Blood Pressure",
        description: "Restorative poses and paced breathing designed to soothe arterial pressure and support heart care.",
        category: "Blood Pressure",
        duration: "15 min",
        icon: "fa-heart-pulse",
        tags: ["blood_pressure", "hypertension", "yoga", "heart_health", "stress"]
    },
    {
        id: "5qap5aO4i9A",
        title: "Mindful Music & Relaxation for Blood Pressure & Sleep",
        description: "Soothing audio ambience to help reduce blood pressure spikes, lower pulse, and calm your nervous system.",
        category: "Hydration",
        duration: "60 min",
        icon: "fa-droplet",
        tags: ["water", "hydration", "blood_pressure", "relaxation", "stress"]
    }
];

/**
 * Filter videos based on user health parameters
 */
function getRecommendedVideosForProfile(healthData = {}, sentimentData = {}) {
    const matchedVideos = [];
    const addedIds = new Set();

    const addVideo = (vid) => {
        if (!addedIds.has(vid.id)) {
            addedIds.add(vid.id);
            matchedVideos.push(vid);
        }
    };

    // 1. High Stress Level check
    const stress = String(healthData.stress_level || '').toLowerCase();
    if (stress === 'high' || stress === 'very high' || stress === 'extreme') {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('stress')).forEach(addVideo);
    }

    // 2. High BMI check (>= 25)
    const bmi = parseFloat(healthData.bmi) || 0;
    if (bmi >= 25) {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('bmi') || v.tags.includes('weight_loss')).forEach(addVideo);
    }

    // 3. Low Water Intake (< 2.0 L)
    const water = parseFloat(healthData.water_intake) || 0;
    if (water > 0 && water < 2.0) {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('water')).forEach(addVideo);
    }

    // 4. Low Exercise Frequency (< 3 days/week)
    const exercise = parseFloat(healthData.exercise_frequency) || 0;
    if (exercise >= 0 && exercise < 3) {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('exercise')).forEach(addVideo);
    }

    // 5. High Blood Pressure check (Systolic >= 130 or Diastolic >= 85 or text contains High)
    const bp = String(healthData.blood_pressure || '');
    if (bp.toLowerCase().includes('high') || bp.includes('130/') || bp.includes('140/') || bp.includes('150/')) {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('blood_pressure')).forEach(addVideo);
    }

    // 6. High Blood Sugar check (>= 125 mg/dL)
    const sugar = parseFloat(healthData.blood_sugar) || 0;
    if (sugar >= 125 || String(healthData.blood_sugar || '').toLowerCase().includes('high')) {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('blood_sugar') || v.tags.includes('weight_loss')).forEach(addVideo);
    }

    // 7. High Mental Health Risk check
    const mentalRisk = String(sentimentData.risk_level || healthData.mental_risk || '').toLowerCase();
    if (mentalRisk.includes('high') || mentalRisk.includes('at-risk') || mentalRisk.includes('critical')) {
        HEALTH_VIDEO_DATABASE.filter(v => v.tags.includes('mental_health')).forEach(addVideo);
    }

    // Fallback: If no specific triggers hit, return balanced default videos across categories
    if (matchedVideos.length === 0) {
        return HEALTH_VIDEO_DATABASE.slice(0, 6);
    }

    return matchedVideos;
}

/**
 * Filter videos based on search query term
 */
function searchHealthVideos(query) {
    if (!query || !query.trim()) return HEALTH_VIDEO_DATABASE;
    const q = query.toLowerCase().trim();

    return HEALTH_VIDEO_DATABASE.filter(v => {
        return v.title.toLowerCase().includes(q) ||
               v.description.toLowerCase().includes(q) ||
               v.category.toLowerCase().includes(q) ||
               v.tags.some(tag => tag.toLowerCase().includes(q));
    });
}

/**
 * Render Video Section inside container element
 */
function renderHealthVideosSection(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    let initialVideos = options.videos || HEALTH_VIDEO_DATABASE.slice(0, 6);
    if (options.autoFilterProfile) {
        initialVideos = getRecommendedVideosForProfile(options.healthData || {}, options.sentimentData || {});
    }

    container.innerHTML = `
        <div class="video-section-wrapper glass-card" style="margin-top: 30px; padding: 28px; border-radius: 20px;">
            <!-- Header -->
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px; margin-bottom: 22px;">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div style="width: 48px; height: 48px; border-radius: 14px; background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); display: flex; align-items: center; justify-content: center; font-size: 22px; color: #fff; box-shadow: 0 6px 20px rgba(239, 68, 68, 0.35);">
                        <i class="fab fa-youtube"></i>
                    </div>
                    <div>
                        <h2 style="font-size: 22px; font-weight: 800; margin: 0; background: linear-gradient(135deg, #ffffff 40%, #94a3b8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                            Recommended Health Videos
                        </h2>
                        <p style="font-size: 13px; color: var(--text-secondary); margin: 3px 0 0;">
                            Personalized educational health, fitness, yoga, and meditation videos tailored to your wellness needs.
                        </p>
                    </div>
                </div>

                <!-- Search Input -->
                <div style="position: relative; min-width: 240px; flex-shrink: 0;">
                    <i class="fas fa-search" style="position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--text-muted); font-size: 13px;"></i>
                    <input type="text" id="${containerId}-search" class="video-search-input" placeholder="Search videos (e.g. Yoga, Weight Loss, Stress)..."
                           style="width: 100%; padding: 9px 14px 9px 38px; border-radius: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.12); color: #fff; font-size: 13px;">
                </div>
            </div>

            <!-- Topic Quick-Filter Pills -->
            <div class="video-topic-chips" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px;">
                <button class="topic-chip active" data-topic="all"><i class="fas fa-grid-2"></i> All Videos</button>
                <button class="topic-chip" data-topic="Yoga"><i class="fas fa-spa"></i> Yoga</button>
                <button class="topic-chip" data-topic="Meditation"><i class="fas fa-om"></i> Meditation</button>
                <button class="topic-chip" data-topic="Weight Loss"><i class="fas fa-fire"></i> Weight Loss</button>
                <button class="topic-chip" data-topic="Stretching"><i class="fas fa-child-reaching"></i> Stretching</button>
                <button class="topic-chip" data-topic="Exercise"><i class="fas fa-dumbbell"></i> Exercise</button>
                <button class="topic-chip" data-topic="Blood Pressure"><i class="fas fa-heart-pulse"></i> Blood Pressure</button>
                <button class="topic-chip" data-topic="Hydration"><i class="fas fa-droplet"></i> Hydration</button>
            </div>

            <!-- Video Grid -->
            <div id="${containerId}-grid" class="video-grid">
                ${generateVideoCardsHTML(initialVideos)}
            </div>
        </div>
    `;

    // Bind Search Input Handler
    const searchInput = document.getElementById(`${containerId}-search`);
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value;
            const filtered = searchHealthVideos(query);
            const grid = document.getElementById(`${containerId}-grid`);
            if (grid) {
                grid.innerHTML = generateVideoCardsHTML(filtered);
            }
            // Clear chip active state if typing search
            container.querySelectorAll('.topic-chip').forEach(chip => chip.classList.remove('active'));
        });
    }

    // Bind Topic Chips Handler
    container.querySelectorAll('.topic-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            container.querySelectorAll('.topic-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');

            const topic = chip.getAttribute('data-topic');
            if (searchInput) searchInput.value = '';

            let filtered = HEALTH_VIDEO_DATABASE;
            if (topic !== 'all') {
                filtered = HEALTH_VIDEO_DATABASE.filter(v => v.category === topic || v.tags.includes(topic.toLowerCase().replace(/\s+/g, '_')));
            }
            const grid = document.getElementById(`${containerId}-grid`);
            if (grid) {
                grid.innerHTML = generateVideoCardsHTML(filtered);
            }
        });
    });
}

/**
 * Generate HTML string for Video Cards Grid
 */
function generateVideoCardsHTML(videos) {
    if (!videos || videos.length === 0) {
        return `
            <div style="grid-column: 1 / -1; text-align: center; padding: 40px 20px; color: var(--text-secondary);">
                <i class="fas fa-video-slash" style="font-size: 36px; margin-bottom: 12px; opacity: 0.5;"></i>
                <p style="font-size: 14px; margin: 0;">No videos found matching your query. Try searching another health topic like 'Yoga' or 'Exercise'.</p>
            </div>
        `;
    }

    return videos.map(vid => `
        <div class="video-card" id="vcard-${vid.id}">
            <!-- Embedded Player Container -->
            <div class="video-thumb-wrapper" id="vwrap-${vid.id}">
                <img src="https://img.youtube.com/vi/${vid.id}/hqdefault.jpg" alt="${vid.title}" class="video-thumb-img" loading="lazy">
                <div class="video-duration-badge"><i class="far fa-clock"></i> ${vid.duration}</div>
                <button class="video-play-overlay" onclick="playInlineVideo('${vid.id}')" title="Play Video">
                    <div class="play-btn-circle"><i class="fas fa-play"></i></div>
                </button>
            </div>

            <!-- Card Body -->
            <div class="video-card-body">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px;">
                    <span class="video-category-tag"><i class="fas ${vid.icon || 'fa-heart-pulse'}"></i> ${vid.category}</span>
                </div>
                <h4 class="video-card-title">${vid.title}</h4>
                <p class="video-card-desc">${vid.description}</p>

                <!-- Actions -->
                <div class="video-card-actions">
                    <button type="button" class="btn-watch-inline" onclick="playInlineVideo('${vid.id}')">
                        <i class="fas fa-circle-play"></i> Watch Here
                    </button>
                    <a href="https://www.youtube.com/watch?v=${vid.id}" target="_blank" rel="noopener noreferrer" class="btn-watch-yt" title="Watch on YouTube">
                        <i class="fab fa-youtube"></i> YouTube <i class="fas fa-arrow-up-right-from-square" style="font-size: 10px;"></i>
                    </a>
                </div>
            </div>
        </div>
    `).join('');
}

/**
 * Replace thumbnail with interactive YouTube iframe embed
 */
function playInlineVideo(videoId) {
    const wrapper = document.getElementById(`vwrap-${videoId}`);
    if (wrapper) {
        wrapper.innerHTML = `
            <iframe class="video-embed-iframe"
                src="https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0"
                title="YouTube Video Player"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowfullscreen>
            </iframe>
        `;
    }
}
