// Frontend Logic - Employee Wellness Management Analytics

// Immediate Theme Initialization
(function() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    if (savedTheme === 'light') {
        document.documentElement.classList.add('light-theme');
        document.addEventListener('DOMContentLoaded', () => {
            if (document.body) document.body.classList.add('light-theme');
        });
    }
})();

document.addEventListener('DOMContentLoaded', () => {
    // Determine which view we are on (Index or Dashboard)
    const isDashboard = document.getElementById('dashboard-view') !== null;

    if (isDashboard) {
        initDashboard();
    } else {
        initAuth();
    }
});

// --- Authentication View Code ---
function initAuth() {
    const tabLogin = document.getElementById('tab-login');
    const tabRegister = document.getElementById('tab-register');
    const tabAdmin = document.getElementById('tab-admin');
    
    const panelLogin = document.getElementById('panel-login');
    const panelRegister = document.getElementById('panel-register');
    const panelAdmin = document.getElementById('panel-admin');
    const panelForgot = document.getElementById('panel-forgot');

    const formLogin = document.getElementById('form-login');
    const formRegister = document.getElementById('form-register');
    const formAdmin = document.getElementById('form-admin');
    const formForgot = document.getElementById('form-forgot');

    const alertLogin = document.getElementById('alert-login');
    const alertRegister = document.getElementById('alert-register');
    const alertAdmin = document.getElementById('alert-admin');
    const alertForgot = document.getElementById('alert-forgot');
    const alertOtp = document.getElementById('alert-otp');

    const linkForgotPassword = document.getElementById('link-forgot-password');
    const linkBackLogin = document.getElementById('link-back-login');
    const authTabs = document.querySelector('.auth-tabs');

    const regPassword = document.getElementById('reg-password');
    const strengthProgress = document.getElementById('strength-progress');
    const strengthText = document.getElementById('strength-text');

    let lockoutInterval = null;

    // Tab Switching
    if (tabLogin && tabRegister && tabAdmin) {
        tabLogin.addEventListener('click', () => {
            tabLogin.classList.add('active');
            tabRegister.classList.remove('active');
            tabAdmin.classList.remove('active');
            panelLogin.classList.add('active');
            panelRegister.classList.remove('active');
            panelAdmin.classList.remove('active');
            if (panelForgot) panelForgot.classList.remove('active');
            clearAlerts();
        });

        tabRegister.addEventListener('click', () => {
            tabRegister.classList.add('active');
            tabLogin.classList.remove('active');
            tabAdmin.classList.remove('active');
            panelRegister.classList.add('active');
            panelLogin.classList.remove('active');
            panelAdmin.classList.remove('active');
            if (panelForgot) panelForgot.classList.remove('active');
            clearAlerts();
        });

        tabAdmin.addEventListener('click', () => {
            tabAdmin.classList.add('active');
            tabLogin.classList.remove('active');
            tabRegister.classList.remove('active');
            panelAdmin.classList.add('active');
            panelLogin.classList.remove('active');
            panelRegister.classList.remove('active');
            if (panelForgot) panelForgot.classList.remove('active');
            clearAlerts();
        });
    }

    // Forgot Password Panel Toggle
    if (linkForgotPassword) {
        linkForgotPassword.addEventListener('click', (e) => {
            e.preventDefault();
            panelLogin.classList.remove('active');
            panelRegister.classList.remove('active');
            panelAdmin.classList.remove('active');
            tabLogin.classList.remove('active');
            tabRegister.classList.remove('active');
            tabAdmin.classList.remove('active');
            panelForgot.classList.add('active');
            clearAlerts();
        });
    }

    // Back to Login Panel Toggle
    if (linkBackLogin) {
        linkBackLogin.addEventListener('click', (e) => {
            e.preventDefault();
            panelForgot.classList.remove('active');
            tabLogin.click();
        });
    }

    // Back to Login Button Toggle
    const btnBackLogin = document.getElementById('back-to-login');
    if (btnBackLogin) {
        btnBackLogin.addEventListener('click', () => {
            tabLogin.click();
        });
    }

    // Toggle Password Visibility
    document.querySelectorAll('.password-toggle').forEach(toggle => {
        toggle.addEventListener('click', (e) => {
            const input = e.target.parentElement.querySelector('input');
            if (input.type === 'password') {
                input.type = 'text';
                e.target.classList.replace('fa-eye-slash', 'fa-eye');
            } else {
                input.type = 'password';
                e.target.classList.replace('fa-eye', 'fa-eye-slash');
            }
        });
    });

    // Password Strength Checker
    if (regPassword) {
        regPassword.addEventListener('input', () => {
            const val = regPassword.value;
            let score = 0;

            if (val.length >= 6) score++;
            if (/[A-Z]/.test(val)) score++;
            if (/[0-9]/.test(val)) score++;
            if (/[^A-Za-z0-9]/.test(val)) score++;

            // Update UI based on score
            let width = '0%';
            let color = 'var(--danger)';
            let text = 'Too Short';

            if (val.length > 0) {
                if (score === 1) {
                    width = '25%';
                    color = 'var(--danger)';
                    text = 'Weak (Needs uppercase, numbers, or symbols)';
                } else if (score === 2) {
                    width = '50%';
                    color = 'var(--warning)';
                    text = 'Medium (Add numbers or symbols)';
                } else if (score === 3) {
                    width = '75%';
                    color = 'var(--secondary)';
                    text = 'Good (Almost there)';
                } else if (score === 4) {
                    width = '100%';
                    color = 'var(--success)';
                    text = 'Strong & Secure';
                }
            } else {
                text = '';
            }

            strengthProgress.style.width = width;
            strengthProgress.style.backgroundColor = color;
            strengthText.textContent = text;
        });
    }

    // Login Form Handler
    if (formLogin) {
        formLogin.addEventListener('submit', async (e) => {
            e.preventDefault();
            clearAlerts();

            const username = document.getElementById('login-username').value;
            const password = document.getElementById('login-password').value;

            const submitBtn = formLogin.querySelector('.btn-submit');
            const origBtnHtml = submitBtn.innerHTML;

            // Set loading spinner
            setLoading(submitBtn, true);

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    if (data.requires_2fa) {
                        setLoading(submitBtn, false, origBtnHtml);
                        showAlert(alertLogin, 'success', 'OTP sent to registered email. Please verify.');
                        
                        // Show OTP Modal Overlay
                        const otpModal = document.getElementById('otp-modal-overlay');
                        if (otpModal) {
                            otpModal.classList.add('active');
                            const otpInput = document.getElementById('otp-input');
                            if (otpInput) {
                                otpInput.value = '';
                                otpInput.focus();
                            }
                        }
                    } else {
                        showAlert(alertLogin, 'success', 'Login Successful! Redirecting...');
                        setTimeout(() => {
                            window.location.href = data.redirect_url || '/dashboard';
                        }, 1200);
                    }
                } else {
                    setLoading(submitBtn, false, origBtnHtml);
                    if (data.locked) {
                        // Enforce Lockout screen
                        showLockoutScreen(data.cooldown_seconds || 300);
                    } else if (data.remaining_attempts !== undefined) {
                        showAlert(alertLogin, 'error', `${data.message} Remaining Attempts: ${data.remaining_attempts}`);
                    } else {
                        showAlert(alertLogin, 'error', data.message);
                    }
                }
            } catch (err) {
                setLoading(submitBtn, false, origBtnHtml);
                showAlert(alertLogin, 'error', 'An error occurred. Please check server connection.');
            }
        });
    }

    // Admin Login Form Handler
    if (formAdmin) {
        formAdmin.addEventListener('submit', async (e) => {
            e.preventDefault();
            clearAlerts();

            const username = document.getElementById('admin-username').value.trim();
            const password = document.getElementById('admin-password').value;

            const submitBtn = formAdmin.querySelector('.btn-submit');
            const origBtnHtml = submitBtn.innerHTML;

            setLoading(submitBtn, true);

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, is_admin_login: true })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    showAlert(alertAdmin, 'success', 'Admin Verification Successful! Loading Portal...');
                    setTimeout(() => {
                        window.location.href = data.redirect_url || '/admin';
                    }, 1200);
                } else {
                    setLoading(submitBtn, false, origBtnHtml);
                    if (data.locked) {
                        showLockoutScreen(data.cooldown_seconds || 300);
                    } else if (data.remaining_attempts !== undefined) {
                        showAlert(alertAdmin, 'error', `${data.message} Remaining Attempts: ${data.remaining_attempts}`);
                    } else {
                        showAlert(alertAdmin, 'error', data.message);
                    }
                }
            } catch (err) {
                setLoading(submitBtn, false, origBtnHtml);
                showAlert(alertAdmin, 'error', 'An error occurred. Please check server connection.');
            }
        });
    }

    // Registration Form — Real-time Uniqueness Validation
    // Tracks per-field uniqueness state (false = OK, true = duplicate)
    const regUnique = { username: false, email: false, employee_id: false };

    /**
     * Show or clear an inline hint message beneath a form input.
     * @param {string} fieldId  - The input element id
     * @param {string|null} msg - Message text (null / '' clears the hint)
     * @param {boolean} isError - Red if true, green if false
     */
    function setFieldHint(fieldId, msg, isError) {
        const input = document.getElementById(fieldId);
        if (!input) return;
        const wrapper = input.closest('.form-group') || input.parentElement;
        let hint = wrapper.querySelector('.field-hint');
        if (!hint) {
            hint = document.createElement('span');
            hint.className = 'field-hint';
            hint.style.cssText = 'display:block;font-size:12px;margin-top:5px;font-weight:500;transition:opacity 0.2s;';
            wrapper.appendChild(hint);
        }
        if (!msg) {
            hint.textContent = '';
            hint.style.opacity = '0';
            return;
        }
        hint.textContent = msg;
        hint.style.color = isError ? '#f87171' : '#34d399';
        hint.style.opacity = '1';
    }

    /**
     * Call /api/check-uniqueness for a single field and update state + hint.
     * @param {string} field      - 'username' | 'email' | 'employee_id'
     * @param {string} value      - Current field value
     * @param {string} inputId    - DOM id of the input
     * @param {string} label      - Human-readable label for message
     */
    async function checkFieldUniqueness(field, value, inputId, label) {
        if (!value) { setFieldHint(inputId, null, false); regUnique[field] = false; return; }
        try {
            const res = await fetch('/api/check-uniqueness', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [field]: value })
            });
            const data = await res.json();
            if (data.success && data.taken[field]) {
                regUnique[field] = true;
                setFieldHint(inputId, `✖ This ${label} is already taken.`, true);
            } else {
                regUnique[field] = false;
                setFieldHint(inputId, `✔ ${label} is available.`, false);
            }
        } catch (_) {
            // silently ignore network errors on blur — backend will still validate on submit
            regUnique[field] = false;
        }
    }

    // Attach blur listeners to the three unique fields
    const empIdInput  = document.getElementById('reg-employee-id');
    const regUsnInput = document.getElementById('reg-username');
    const regEmlInput = document.getElementById('reg-email');

    if (empIdInput) {
        empIdInput.addEventListener('blur', () => {
            checkFieldUniqueness('employee_id', empIdInput.value.trim(), 'reg-employee-id', 'Employee ID');
        });
        empIdInput.addEventListener('input', () => {
            // Clear stale hint while typing
            setFieldHint('reg-employee-id', null, false);
            regUnique.employee_id = false;
        });
    }

    if (regUsnInput) {
        regUsnInput.addEventListener('blur', () => {
            checkFieldUniqueness('username', regUsnInput.value.trim(), 'reg-username', 'Username');
        });
        regUsnInput.addEventListener('input', () => {
            setFieldHint('reg-username', null, false);
            regUnique.username = false;
        });
    }

    if (regEmlInput) {
        regEmlInput.addEventListener('blur', () => {
            if (regEmlInput.value.trim()) {
                checkFieldUniqueness('email', regEmlInput.value.trim(), 'reg-email', 'Email address');
            }
        });
        regEmlInput.addEventListener('input', () => {
            setFieldHint('reg-email', null, false);
            regUnique.email = false;
        });
    }

    // Registration Form Submit Handler
    if (formRegister) {
        formRegister.addEventListener('submit', async (e) => {
            e.preventDefault();
            clearAlerts();

            const username = document.getElementById('reg-username').value.trim();
            const email = document.getElementById('reg-email').value.trim();
            const mobile = document.getElementById('reg-mobile').value.trim();
            const password = document.getElementById('reg-password').value;
            const confirmPassword = document.getElementById('reg-confirm').value;
            const jobRole = document.getElementById('reg-jobrole').value;
            const employeeId = document.getElementById('reg-employee-id').value.trim();

            if (!email.includes('@')) {
                showAlert(alertRegister, 'error', 'Email address must contain @.');
                return;
            }

            if (!/^\d{10}$/.test(mobile)) {
                showAlert(alertRegister, 'error', 'Mobile number must be exactly 10 digits.');
                return;
            }

            if (password !== confirmPassword) {
                showAlert(alertRegister, 'error', 'Passwords do not match.');
                return;
            }

            // --- Uniqueness guard: re-check all three fields before submitting ---
            const submitBtn = formRegister.querySelector('.btn-submit');
            const origBtnHtml = submitBtn.innerHTML;
            setLoading(submitBtn, true);

            try {
                const checkRes = await fetch('/api/check-uniqueness', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, employee_id: employeeId })
                });
                const checkData = await checkRes.json();

                if (checkData.success) {
                    const taken = checkData.taken;
                    const dupeErrors = [];
                    if (taken.employee_id) {
                        dupeErrors.push('Employee ID is already in use');
                        setFieldHint('reg-employee-id', '✖ This Employee ID is already taken.', true);
                        regUnique.employee_id = true;
                    }
                    if (taken.username) {
                        dupeErrors.push('Username is already taken');
                        setFieldHint('reg-username', '✖ This Username is already taken.', true);
                        regUnique.username = true;
                    }
                    if (taken.email) {
                        dupeErrors.push('Email is already registered');
                        setFieldHint('reg-email', '✖ This Email address is already registered.', true);
                        regUnique.email = true;
                    }
                    if (dupeErrors.length > 0) {
                        setLoading(submitBtn, false, origBtnHtml);
                        showAlert(alertRegister, 'error', dupeErrors.join(' · ') + '. Please use unique values.');
                        return;
                    }
                }
            } catch (_) {
                // If uniqueness check fails, still proceed — backend will catch duplicates
            }

            const fullName = document.getElementById('reg-fullname').value.trim();
            const dob = document.getElementById('reg-dob').value;
            const genderVal = document.querySelector('input[name="reg-gender"]:checked') ? document.querySelector('input[name="reg-gender"]:checked').value : '';

            const formData = new FormData();
            formData.append('username', username);
            formData.append('email', email);
            formData.append('password', password);
            formData.append('job_role', jobRole);
            formData.append('fullname', fullName);
            formData.append('employee_id', employeeId);
            formData.append('mobile_number', mobile);
            formData.append('gender', genderVal);
            formData.append('dob', dob);

            const photoInput = document.getElementById('reg-photo');
            if (photoInput && photoInput.files.length > 0) {
                formData.append('profile_photo', photoInput.files[0]);
            }

            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                setLoading(submitBtn, false, origBtnHtml);

                if (response.ok && data.success) {
                    showAlert(alertRegister, 'success', 'Registration Successful! Switching to Login...');
                    formRegister.reset();
                    // Clear all field hints on successful registration
                    ['reg-employee-id', 'reg-username', 'reg-email'].forEach(id => setFieldHint(id, null, false));
                    regUnique.username = false; regUnique.email = false; regUnique.employee_id = false;
                    if (strengthProgress) strengthProgress.style.width = '0%';
                    if (strengthText) strengthText.textContent = '';

                    setTimeout(() => {
                        tabLogin.click();
                    }, 2000);
                } else {
                    showAlert(alertRegister, 'error', data.message);
                }
            } catch (err) {
                setLoading(submitBtn, false, origBtnHtml);
                showAlert(alertRegister, 'error', 'An error occurred. Please check server connection.');
            }
        });
    }


    // Forgot Password Form Handler
    if (formForgot) {
        formForgot.addEventListener('submit', async (e) => {
            e.preventDefault();
            clearAlerts();

            // Auto-grab username from the Sign In field
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('forgot-password').value;
            const confirmPassword = document.getElementById('forgot-confirm-password').value;

            if (!username) {
                showAlert(alertForgot, 'error', 'Please enter your username in the Sign In page first.');
                return;
            }

            if (!password || !confirmPassword) {
                showAlert(alertForgot, 'error', 'Both password fields are required.');
                return;
            }

            if (password !== confirmPassword) {
                showAlert(alertForgot, 'error', 'Passwords do not match.');
                return;
            }

            if (password.length < 6) {
                showAlert(alertForgot, 'error', 'New password must be at least 6 characters.');
                return;
            }

            const submitBtn = formForgot.querySelector('.btn-submit');
            const origBtnHtml = submitBtn.innerHTML;
            setLoading(submitBtn, true);

            try {
                const response = await fetch('/api/forgot-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();
                setLoading(submitBtn, false, origBtnHtml);

                if (response.ok && data.success) {
                    showAlert(alertForgot, 'success', 'Password reset successful! Switching to Sign In...');
                    formForgot.reset();
                    setTimeout(() => {
                        linkBackLogin.click();
                    }, 2000);
                } else {
                    showAlert(alertForgot, 'error', data.message);
                }
            } catch (err) {
                setLoading(submitBtn, false, origBtnHtml);
                showAlert(alertForgot, 'error', 'An error occurred. Please check server connection.');
            }
        });
    }

    function clearAlerts() {
        if (alertLogin) {
            alertLogin.style.display = 'none';
            alertLogin.className = 'alert-box';
        }
        if (alertRegister) {
            alertRegister.style.display = 'none';
            alertRegister.className = 'alert-box';
        }
        if (alertAdmin) {
            alertAdmin.style.display = 'none';
            alertAdmin.className = 'alert-box';
        }
        if (alertForgot) {
            alertForgot.style.display = 'none';
            alertForgot.className = 'alert-box';
        }
        if (alertOtp) {
            alertOtp.style.display = 'none';
            alertOtp.className = 'alert-box';
        }
    }

    // Handles the custom 3-attempt Lockout countdown UI inside the card
    function showLockoutScreen(totalSeconds) {
        const cardBody = document.querySelector('.glass-card');
        const originalContent = cardBody.innerHTML;

        cardBody.innerHTML = `
            <div class="lockout-message">
                <i class="fas fa-user-lock lockout-icon"></i>
                <h3 class="project-title" style="margin-bottom: 10px;">Security Lockout</h3>
                <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
                    Your account has been temporarily locked due to too many failed login attempts.
                </p>
                <div class="cooldown-timer" id="timer-display">00:00</div>
                <p style="color: var(--text-muted); font-size: 12px; margin-top: 10px;">
                    Please wait until the timer expires to try logging in again.
                </p>
            </div>
        `;

        let secondsLeft = totalSeconds;

        const updateTimer = () => {
            const min = Math.floor(secondsLeft / 60);
            const sec = secondsLeft % 60;
            const minStr = min < 10 ? '0' + min : min;
            const secStr = sec < 10 ? '0' + sec : sec;

            const timerDisplay = document.getElementById('timer-display');
            if (timerDisplay) {
                timerDisplay.textContent = `${minStr}:${secStr}`;
            }

            if (secondsLeft <= 0) {
                clearInterval(lockoutInterval);
                // Restore card body to original state
                cardBody.innerHTML = originalContent;
                // Re-bind listeners by re-initializing auth
                initAuth();
            }
            secondsLeft--;
        };

        updateTimer();
        lockoutInterval = setInterval(updateTimer, 1000);
    }
}

// --- Dashboard View Code ---
function initDashboard() {
    initSidebarAndModal();
    initNotifications();

    // Theme Toggle Handler
    const toggleTheme = document.getElementById('toggle-theme');
    if (toggleTheme) {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        toggleTheme.checked = (savedTheme === 'light');

        toggleTheme.addEventListener('change', () => {
            if (toggleTheme.checked) {
                localStorage.setItem('theme', 'light');
                document.documentElement.classList.add('light-theme');
                document.body.classList.add('light-theme');
            } else {
                localStorage.setItem('theme', 'dark');
                document.documentElement.classList.remove('light-theme');
                document.body.classList.remove('light-theme');
            }
        });
    }

    // Clear All Logs Button Handler
    const btnClearLogs = document.getElementById('btn-clear-logs');
    if (btnClearLogs) {
        btnClearLogs.addEventListener('click', async () => {
            const confirmed = confirm('Are you sure you want to clear ALL login logs? This action cannot be undone.');
            if (!confirmed) return;

            btnClearLogs.disabled = true;
            btnClearLogs.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Clearing...';

            try {
                const response = await fetch('/api/clear-logs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    // Reload page to reflect cleared logs
                    window.location.reload();
                } else {
                    alert('Failed to clear logs: ' + data.message);
                    btnClearLogs.disabled = false;
                    btnClearLogs.innerHTML = '<i class="fas fa-trash-alt"></i> Clear All Logs';
                }
            } catch (err) {
                alert('An error occurred while clearing logs.');
                btnClearLogs.disabled = false;
                btnClearLogs.innerHTML = '<i class="fas fa-trash-alt"></i> Clear All Logs';
            }
        });
    }

    // Admin Creation Form Handler
    const formCreateAdmin = document.getElementById('form-create-admin');
    const alertCreateAdmin = document.getElementById('alert-create-admin');

    if (formCreateAdmin) {
        formCreateAdmin.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (alertCreateAdmin) {
                alertCreateAdmin.style.display = 'none';
                alertCreateAdmin.className = 'alert-box';
            }

            const username = document.getElementById('new-admin-username').value.trim();
            const email = document.getElementById('new-admin-email').value.trim();
            const password = document.getElementById('new-admin-password').value;
            const confirmPassword = document.getElementById('new-admin-confirm').value;

            if (password !== confirmPassword) {
                showAlert(alertCreateAdmin, 'error', 'Passwords do not match.');
                return;
            }

            const submitBtn = formCreateAdmin.querySelector('.btn-submit');
            const origBtnHtml = submitBtn.innerHTML;
            setLoading(submitBtn, true);

            try {
                const response = await fetch('/api/admin/create-admin', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, password })
                });

                const data = await response.json();
                setLoading(submitBtn, false, origBtnHtml);

                if (response.ok && data.success) {
                    showAlert(alertCreateAdmin, 'success', 'Admin account created successfully!');
                    formCreateAdmin.reset();
                } else {
                    showAlert(alertCreateAdmin, 'error', data.message);
                }
            } catch (err) {
                setLoading(submitBtn, false, origBtnHtml);
                showAlert(alertCreateAdmin, 'error', 'An error occurred. Please check server connection.');
            }
        });
    }

    // OTP Modal and Form Elements
    const otpModal = document.getElementById('otp-modal-overlay');
    const formOtp = document.getElementById('form-otp');
    const otpInput = document.getElementById('otp-input');
    const btnOtpCancel = document.getElementById('btn-otp-cancel');

    if (otpModal && formOtp && otpInput) {
        // Cancel button closes OTP modal
        if (btnOtpCancel) {
            btnOtpCancel.addEventListener('click', () => {
                otpModal.classList.remove('active');
                if (alertOtp) {
                    alertOtp.style.display = 'none';
                    alertOtp.className = 'alert-box';
                }
            });
        }

        // OTP form submit handler
        formOtp.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (alertOtp) {
                alertOtp.style.display = 'none';
                alertOtp.className = 'alert-box';
            }

            const otp = otpInput.value.trim();
            const submitBtn = formOtp.querySelector('.btn-submit') || document.getElementById('btn-otp-confirm');
            const origBtnHtml = submitBtn ? submitBtn.innerHTML : 'Verify';

            if (submitBtn) setLoading(submitBtn, true);

            try {
                const response = await fetch('/api/login/verify-2fa', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ otp })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    if (alertOtp) showAlert(alertOtp, 'success', '2FA Verified! Redirecting...');
                    setTimeout(() => {
                        window.location.href = data.redirect_url || '/dashboard';
                    }, 1200);
                } else {
                    if (submitBtn) setLoading(submitBtn, false, origBtnHtml);
                    if (alertOtp) showAlert(alertOtp, 'error', data.message || 'Verification failed.');
                }
            } catch (err) {
                if (submitBtn) setLoading(submitBtn, false, origBtnHtml);
                if (alertOtp) showAlert(alertOtp, 'error', 'An error occurred. Please check server connection.');
            }
        });
    }
}

// --- Global Helper Functions ---
function showAlert(element, type, message) {
    if (!element) return;
    element.style.display = 'flex';
    element.className = `alert-box alert-${type}`;
    element.querySelector('.alert-msg').textContent = message;
}

function setLoading(btn, isLoading, originalHtml = '') {
    if (isLoading) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="spinner" viewBox="0 0 50 50">
                <circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="5"></circle>
            </svg>
            Processing...
        `;
    } else {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

function initSidebarAndModal() {
    const hamburger = document.getElementById('btn-hamburger') || document.getElementById('btn-sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const closeBtn = document.getElementById('btn-sidebar-close');
    const overlay = document.getElementById('sidebar-overlay');

    if (hamburger && sidebar && closeBtn && overlay) {
        const toggleSidebar = (show) => {
            if (show) {
                sidebar.classList.add('active');
                overlay.classList.add('active');
            } else {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            }
        };

        hamburger.addEventListener('click', () => toggleSidebar(true));
        closeBtn.addEventListener('click', () => toggleSidebar(false));
        overlay.addEventListener('click', () => toggleSidebar(false));
    }

    // Modal Logout bindings
    const logoutBtn = document.getElementById('btn-logout');
    const sidebarLogoutBtn = document.getElementById('btn-sidebar-logout');
    const logoutModal = document.getElementById('logout-modal-overlay');
    const cancelLogout = document.getElementById('btn-logout-cancel');
    const confirmLogout = document.getElementById('btn-logout-confirm');

    if (logoutModal && cancelLogout && confirmLogout) {
        const showModal = (show) => {
            if (show) {
                logoutModal.classList.add('active');
            } else {
                logoutModal.classList.remove('active');
            }
        };

        (function () {
            // Existing loadDashboardStats function
            function loadDashboardStats() {
                fetch('/api/dashboard-stats')
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) return;
                        var s = data.stats;
                        animateCount(document.getElementById('stat-total'),   s.total_employees,    900);
                        animateCount(document.getElementById('stat-healthy'),  s.healthy_employees,  900);
                        animateCount(document.getElementById('stat-risk'),     s.high_risk_employees, 900);
                        animateCount(document.getElementById('stat-pending'),  s.pending_assessments, 900);
                    })
                    .catch(function () {
                        ['stat-total','stat-healthy','stat-risk','stat-pending'].forEach(function(id) {
                            var el = document.getElementById(id);
                            if (el) { el.classList.remove('loading'); el.textContent = '-'; }
                        });
                    });
            }
            // New function to load health score for the logged-in user
            function loadHealthScore() {
                fetch('/api/health-score')
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) return;
                        var hs = data.health_score;
                        // Update score value
                        var scoreEl = document.getElementById('stat-health-score');
                        if (scoreEl) { scoreEl.textContent = hs.score; }
                        // Update status label
                        var statusEl = document.getElementById('stat-health-status');
                        if (statusEl) { statusEl.textContent = hs.status; }
                    })
                    .catch(function () {
                        var el = document.getElementById('stat-health-score');
                        if (el) { el.classList.remove('loading'); el.textContent = '-'; }
                        var statEl = document.getElementById('stat-health-status');
                        if (statEl) { statEl.classList.remove('loading'); statEl.textContent = 'Error'; }
                    });
            }
            // Run after DOM is ready
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', function () {
                    loadDashboardStats();
                    loadHealthScore();
                });
            } else {
                loadDashboardStats();
                loadHealthScore();
            }
        })();

        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                showModal(true);
            });
        }

        if (sidebarLogoutBtn) {
            sidebarLogoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (sidebar && overlay) {
                    sidebar.classList.remove('active');
                    overlay.classList.remove('active');
                }
                showModal(true);
            });
        }

        cancelLogout.addEventListener('click', () => showModal(false));

        confirmLogout.addEventListener('click', async () => {
            try {
                const response = await fetch('/api/logout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (response.ok) {
                    window.location.href = '/';
                }
            } catch (err) {
                console.error('Logout error:', err);
                window.location.href = '/';
            }
        });
    }
}

function initNotifications() {
    // 1. Inject styling into document head
    const styleEl = document.createElement('style');
    styleEl.innerHTML = `
        header.dash-header {
            overflow: visible !important;
            z-index: 1001 !important;
        }
        .notification-wrapper {
            position: relative;
            margin-right: 20px;
            display: inline-flex;
            align-items: center;
        }
        .notification-bell {
            position: relative;
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            color: rgba(255, 255, 255, 0.75);
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 16px;
        }
        .notification-bell:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
            color: #fff;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .notification-bell:active {
            transform: translateY(1px);
        }
        .notification-badge {
            position: absolute;
            top: -5px;
            right: -5px;
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            border: 2px solid #0f172a;
            border-radius: 50%;
            color: #fff;
            font-size: 10px;
            font-weight: 700;
            min-width: 19px;
            height: 19px;
            padding: 0 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.5);
            transform: scale(0);
            transition: transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        .notification-badge.show {
            transform: scale(1);
        }

        /* Backdrop overlay when panel is open */
        .notification-backdrop {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 9998;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
        }
        .notification-backdrop.active {
            opacity: 1;
            pointer-events: auto;
        }

        /* Main dropdown panel — fully opaque, solid background */
        .notification-dropdown {
            position: absolute;
            top: 56px;
            right: -10px;
            width: 400px;
            max-height: 560px;
            background: #111827;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 18px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255,255,255,0.05);
            z-index: 9999;
            padding: 0;
            display: flex;
            flex-direction: column;
            opacity: 0;
            transform: translateY(-8px) scale(0.96);
            pointer-events: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .notification-dropdown.active {
            opacity: 1;
            transform: translateY(0) scale(1);
            pointer-events: auto;
        }

        /* Panel header */
        .notification-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 22px 14px 22px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            background: #111827;
            border-radius: 18px 18px 0 0;
        }
        .notification-header-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .notification-header-left i {
            font-size: 16px;
            color: #818cf8;
        }
        .notification-header h4 {
            margin: 0;
            font-size: 16px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: 0.2px;
        }
        .notification-header-actions {
            display: flex;
            gap: 6px;
        }
        .notification-header-actions button {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #94a3b8;
            font-size: 11px;
            cursor: pointer;
            padding: 5px 10px;
            font-weight: 600;
            border-radius: 8px;
            transition: all 0.2s ease;
            white-space: nowrap;
        }
        .notification-header-actions button:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border-color: rgba(255, 255, 255, 0.15);
        }
        .notification-header-actions .btn-clear-all:hover {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.3);
        }

        /* Scrollable notification list */
        .notification-list {
            display: flex;
            flex-direction: column;
            gap: 0;
            overflow-y: auto;
            max-height: 440px;
            padding: 10px 12px 14px 12px;
            background: #111827;
            border-radius: 0 0 18px 18px;
        }
        .notification-list::-webkit-scrollbar {
            width: 5px;
        }
        .notification-list::-webkit-scrollbar-track {
            background: transparent;
        }
        .notification-list::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.12);
            border-radius: 3px;
        }
        .notification-list::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* Individual notification card — solid background, no transparency */
        .notification-item {
            display: flex;
            gap: 14px;
            padding: 14px 16px;
            margin-bottom: 8px;
            border-radius: 14px;
            background: #1e293b;
            border: 1px solid rgba(255, 255, 255, 0.06);
            transition: all 0.2s ease;
            cursor: pointer;
            position: relative;
        }
        .notification-item:last-child {
            margin-bottom: 0;
        }
        .notification-item:hover {
            background: #263348;
            border-color: rgba(255, 255, 255, 0.1);
            transform: translateX(2px);
        }
        .notification-item.read {
            opacity: 0.5;
        }
        .notification-item.read:hover {
            opacity: 0.7;
        }

        /* Unread indicator dot on the card */
        .notification-item.unread::before {
            content: '';
            position: absolute;
            top: 14px;
            right: 14px;
            width: 8px;
            height: 8px;
            background: #818cf8;
            border-radius: 50%;
            box-shadow: 0 0 8px rgba(129, 140, 248, 0.5);
            animation: notifPulse 2s infinite;
        }
        @keyframes notifPulse {
            0%, 100% { box-shadow: 0 0 8px rgba(129, 140, 248, 0.5); }
            50% { box-shadow: 0 0 14px rgba(129, 140, 248, 0.8); }
        }

        /* Icon wrapper */
        .notification-icon-wrapper {
            width: 38px;
            height: 38px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            font-size: 15px;
        }

        /* Type-specific colors — LEFT BORDER + ICON */
        .notification-item.type-info { border-left: 3px solid #06b6d4; }
        .notification-item.type-info .notification-icon-wrapper { background: rgba(6, 182, 212, 0.15); color: #22d3ee; }

        .notification-item.type-warning { border-left: 3px solid #f59e0b; }
        .notification-item.type-warning .notification-icon-wrapper { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }

        .notification-item.type-danger { border-left: 3px solid #ef4444; }
        .notification-item.type-danger .notification-icon-wrapper { background: rgba(239, 68, 68, 0.15); color: #f87171; }

        .notification-item.type-success { border-left: 3px solid #10b981; }
        .notification-item.type-success .notification-icon-wrapper { background: rgba(16, 185, 129, 0.15); color: #34d399; }

        /* Content area */
        .notification-content {
            display: flex;
            flex-direction: column;
            gap: 4px;
            flex-grow: 1;
            min-width: 0;
        }
        .notification-title {
            font-size: 13.5px;
            font-weight: 700;
            color: #ffffff;
            margin: 0;
            line-height: 1.3;
            padding-right: 16px;
        }
        .notification-msg {
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.45;
            margin: 0;
        }
        .notification-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 4px;
        }
        .notification-date {
            font-size: 10.5px;
            color: #64748b;
            font-weight: 500;
        }
        .notification-ago {
            font-size: 10.5px;
            color: #818cf8;
            font-weight: 600;
        }

        /* Empty state */
        .notification-empty {
            text-align: center;
            padding: 45px 20px;
        }
        .notification-empty i {
            font-size: 32px;
            color: #334155;
            margin-bottom: 12px;
            display: block;
        }
        .notification-empty p {
            color: #64748b;
            font-size: 13px;
            font-weight: 500;
            margin: 0;
        }
    `;
    document.head.appendChild(styleEl);

    // 2. Locate container and inject elements
    const userProfile = document.querySelector('header.dash-header .user-profile:last-child');
    if (!userProfile) return;

    // Get current username for localStorage keying
    const welcomeHeader = userProfile.querySelector('h4');
    let username = 'guest';
    if (welcomeHeader) {
        username = welcomeHeader.textContent.replace('Welcome, ', '').trim();
    }

    // Create backdrop element
    const backdrop = document.createElement('div');
    backdrop.className = 'notification-backdrop';
    backdrop.id = 'notification-backdrop';
    document.body.appendChild(backdrop);

    const notificationWrapper = document.createElement('div');
    notificationWrapper.className = 'notification-wrapper';

    notificationWrapper.innerHTML = `
        <div class="notification-bell" id="notification-bell">
            <i class="fas fa-bell"></i>
            <span class="notification-badge" id="notification-badge">0</span>
        </div>
        <div class="notification-dropdown" id="notification-dropdown">
            <div class="notification-header">
                <div class="notification-header-left">
                    <i class="fas fa-bell"></i>
                    <h4>Notifications</h4>
                </div>
                <div class="notification-header-actions">
                    <button id="mark-all-read"><i class="fas fa-check-double"></i> Mark all read</button>
                    <button id="clear-all-notifs" class="btn-clear-all"><i class="fas fa-trash-can"></i> Clear All</button>
                </div>
            </div>
            <div class="notification-list" id="notification-list">
                <div style="text-align: center; color: #64748b; padding: 30px 0; font-size: 12px;">Loading...</div>
            </div>
        </div>
    `;

    // Insert before avatar or as first element
    const avatar = userProfile.querySelector('.avatar');
    if (avatar) {
        userProfile.insertBefore(notificationWrapper, avatar);
    } else {
        userProfile.insertBefore(notificationWrapper, userProfile.firstChild);
    }

    const bell = document.getElementById('notification-bell');
    const dropdown = document.getElementById('notification-dropdown');
    const list = document.getElementById('notification-list');
    const badge = document.getElementById('notification-badge');
    const markAllReadBtn = document.getElementById('mark-all-read');
    const clearAllBtn = document.getElementById('clear-all-notifs');

    let allNotifications = [];
    const readStorageKey = 'read_notifications_' + username;
    const clearedStorageKey = 'cleared_notifications_' + username;

    function getReadIds() {
        try {
            return JSON.parse(localStorage.getItem(readStorageKey)) || [];
        } catch (_) {
            return [];
        }
    }

    function setReadIds(ids) {
        try {
            localStorage.setItem(readStorageKey, JSON.stringify(ids));
        } catch (_) {}
    }

    function getClearedIds() {
        try {
            return JSON.parse(localStorage.getItem(clearedStorageKey)) || [];
        } catch (_) {
            return [];
        }
    }

    function setClearedIds(ids) {
        try {
            localStorage.setItem(clearedStorageKey, JSON.stringify(ids));
        } catch (_) {}
    }

    // Load notifications from server
    async function loadNotifications() {
        try {
            const res = await fetch('/api/notifications');
            const data = await res.json();
            if (data.success) {
                const clearedIds = getClearedIds();
                allNotifications = (data.notifications || []).filter(n => !clearedIds.includes(n.id));
                updateBadge();
                renderList();
            } else {
                list.innerHTML = `<div class="notification-empty"><i class="fas fa-circle-xmark"></i><p>Failed to load notifications.</p></div>`;
            }
        } catch (e) {
            list.innerHTML = `<div class="notification-empty"><i class="fas fa-wifi"></i><p>Network error. Please try again.</p></div>`;
        }
    }

    function updateBadge() {
        const readIds = getReadIds();
        const unreadCount = allNotifications.filter(n => !readIds.includes(n.id)).length;
        if (unreadCount > 0) {
            badge.textContent = unreadCount;
            badge.classList.add('show');
        } else {
            badge.classList.remove('show');
        }
    }

    function renderList() {
        if (allNotifications.length === 0) {
            list.innerHTML = `<div class="notification-empty"><i class="fas fa-bell-slash"></i><p>All caught up! No notifications.</p></div>`;
            return;
        }

        const readIds = getReadIds();
        list.innerHTML = '';

        allNotifications.forEach(n => {
            const isRead = readIds.includes(n.id);
            const item = document.createElement('div');
            item.className = `notification-item type-${n.type} ${isRead ? 'read' : 'unread'}`;

            // Format time ago
            let timeAgo = '';
            let dateTimeStr = '';
            try {
                const dt = new Date(n.timestamp.replace(' ', 'T'));
                if (!isNaN(dt.getTime())) {
                    const diffMs = new Date() - dt;
                    const diffMins = Math.floor(diffMs / 60000);
                    const diffHours = Math.floor(diffMins / 60);
                    const diffDays = Math.floor(diffHours / 24);

                    if (diffMins < 1) timeAgo = 'Just now';
                    else if (diffMins < 60) timeAgo = `${diffMins}m ago`;
                    else if (diffHours < 24) timeAgo = `${diffHours}h ago`;
                    else if (diffDays === 1) timeAgo = 'Yesterday';
                    else if (diffDays < 7) timeAgo = `${diffDays} days ago`;
                    else timeAgo = dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

                    // Full date and time string
                    dateTimeStr = dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) +
                                  ' at ' + dt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                }
            } catch (_) {
                timeAgo = n.timestamp;
                dateTimeStr = n.timestamp;
            }

            item.innerHTML = `
                <div class="notification-icon-wrapper">
                    <i class="fas ${n.icon}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${n.title}</div>
                    <p class="notification-msg">${n.message}</p>
                    <div class="notification-meta">
                        <span class="notification-date"><i class="fas fa-clock" style="margin-right:3px;"></i>${dateTimeStr}</span>
                        <span class="notification-ago">${timeAgo}</span>
                    </div>
                </div>
            `;

            item.addEventListener('click', (e) => {
                e.stopPropagation();
                if (!isRead) {
                    const currentRead = getReadIds();
                    currentRead.push(n.id);
                    setReadIds(currentRead);
                    updateBadge();
                    renderList();
                }
            });

            list.appendChild(item);
        });
    }

    // Toggle Dropdown
    bell.addEventListener('click', (e) => {
        e.stopPropagation();
        const isActive = dropdown.classList.contains('active');

        document.querySelectorAll('.notification-dropdown').forEach(el => el.classList.remove('active'));

        if (!isActive) {
            dropdown.classList.add('active');
            backdrop.classList.add('active');
            loadNotifications();
        } else {
            dropdown.classList.remove('active');
            backdrop.classList.remove('active');
        }
    });

    // Mark all as read
    markAllReadBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const allIds = allNotifications.map(n => n.id);
        setReadIds(allIds);
        updateBadge();
        renderList();
    });

    // Clear All — hides notifications from the panel
    clearAllBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const allIds = allNotifications.map(n => n.id);
        const currentCleared = getClearedIds();
        setClearedIds([...new Set([...currentCleared, ...allIds])]);
        allNotifications = [];
        updateBadge();
        renderList();
    });

    // Close when clicking outside or on backdrop
    document.addEventListener('click', (e) => {
        if (!notificationWrapper.contains(e.target)) {
            dropdown.classList.remove('active');
            backdrop.classList.remove('active');
        }
    });
    backdrop.addEventListener('click', () => {
        dropdown.classList.remove('active');
        backdrop.classList.remove('active');
    });

    // Load initial counts silently on start
    loadNotifications();
}