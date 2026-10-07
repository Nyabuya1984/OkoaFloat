import React, { useEffect, useState } from 'react';
import { Eye, EyeOff, Mail } from 'react-feather';
import './App.css';
import AuthenticatedRoutes from './components/AuthenticatedRoutes';
import { BrowserRouter } from 'react-router-dom';
import { clearAuthSession, getAuthToken, getRefreshToken, saveAuthSession } from './services/authStorage';

const API_ORIGIN = process.env.REACT_APP_API_URL || '';
const AUTH_API_BASE = `${API_ORIGIN}/api/auth`;

const emptyRegistration = {
  employee_name: '',
  job_position_title: '',
  employer: '',
  department: '',
  email: '',
  personal_email: '',
  phone_number: '',
  password: '',
};

const apiError = (payload, fallback) => payload?.error?.message || payload?.error || payload?.message || fallback;

const normalizeUser = (user) => ({
  ...user,
  role: String(user.role || 'employee').trim().replace(/-/g, '_').toLowerCase(),
  department: user.department || user.department_details?.name || user.department_name || '',
  name: user.full_name || user.name || 'Employee',
  phone: user.phone_number,
});

function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authView, setAuthView] = useState('login');
  const [loginPhone, setLoginPhone] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [loginOtp, setLoginOtp] = useState('');
  const [loginOtpSent, setLoginOtpSent] = useState(false);
  const [loginResendCountdown, setLoginResendCountdown] = useState(0);
  const [registration, setRegistration] = useState(emptyRegistration);
  const [registrationOtp, setRegistrationOtp] = useState('');
  const [registrationOtpEmail, setRegistrationOtpEmail] = useState('');
  const [registrationOtpSent, setRegistrationOtpSent] = useState(false);
  const [registrationResendCountdown, setRegistrationResendCountdown] = useState(0);
  const [resetPassword, setResetPassword] = useState('');
  const [resetOtp, setResetOtp] = useState('');
  const [recoveryEmail, setRecoveryEmail] = useState('');
  const [recoveryOtpEmail, setRecoveryOtpEmail] = useState('');
  const [resetOtpSent, setResetOtpSent] = useState(false);
  const [showResetPassword, setShowResetPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (loginResendCountdown <= 0 && registrationResendCountdown <= 0) return undefined;
    const timer = window.setInterval(() => {
      setLoginResendCountdown((value) => Math.max(0, value - 1));
      setRegistrationResendCountdown((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [loginResendCountdown, registrationResendCountdown]);

  const showMessage = (type, text) => setMessage({ type, text });
  const clearMessage = () => setMessage(null);

  const validatePhone = (phone) => {
    const cleaned = phone.replace(/[\s\-()+]/g, '');
    return [/^07\d{8}$/, /^01\d{8}$/, /^254[17]\d{8}$/, /^[17]\d{8}$/].some((pattern) => pattern.test(cleaned));
  };

  const saveSession = (data) => {
    saveAuthSession(data);
    setCurrentUser(normalizeUser(data.user));
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) return;

    fetch(`${AUTH_API_BASE}/me`, {
      cache: 'no-store',
      headers: { Authorization: `Bearer ${token}`, 'Cache-Control': 'no-cache' },
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok || !data.user) throw new Error('Session expired');
        setCurrentUser(normalizeUser(data.user));
      })
      .catch(() => {
        clearAuthSession();
      });
  }, []);

  const submitLogin = async () => {
    clearMessage();
    if (!loginPhone.trim() || !loginPassword.trim()) {
      showMessage('error', 'Enter your phone number and password.');
      return;
    }
    if (!validatePhone(loginPhone.trim())) {
      showMessage('error', 'Enter a valid Kenyan phone number.');
      return;
    }

    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: loginPhone.trim(), password: loginPassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Unable to sign in.'));
      setLoginOtpSent(true);
      setLoginResendCountdown(5);
      showMessage(data.email_sent === false ? 'error' : 'success', data.message || 'A verification code was sent to your work and personal email addresses.');
    } catch (error) {
      showMessage('error', error instanceof TypeError ? 'Cannot reach the leave server. Start the backend on port 5000 and try again.' : error.message);
    } finally {
      setBusy(false);
    }
  };

  const verifyLogin = async () => {
    clearMessage();
    if (loginOtp.trim().length !== 6) {
      showMessage('error', 'Enter the 6-digit verification code.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: loginPhone.trim(), otp: loginOtp.trim() }),
      });
      const data = await response.json();
      if (!response.ok || !data.access_token) throw new Error(apiError(data, 'Invalid verification code.'));
      saveSession(data);
    } catch (error) {
      showMessage('error', error.message);
    } finally {
      setBusy(false);
    }
  };

  const submitRegistration = async () => {
    clearMessage();
    const required = ['employee_name', 'job_position_title', 'employer', 'department', 'email', 'personal_email', 'phone_number', 'password'];
    if (required.some((field) => !registration[field]?.trim())) {
      showMessage('error', 'Complete your employee name, job title, employer, department, work email, personal email, phone number, and password.');
      return;
    }
    if (!validatePhone(registration.phone_number.trim())) {
      showMessage('error', 'Enter a valid Kenyan phone number.');
      return;
    }
    if (registration.password.length < 8) {
      showMessage('error', 'Password must be at least 8 characters.');
      return;
    }

    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...registration, phone_number: registration.phone_number.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Registration failed.'));
      setRegistrationOtpSent(true);
      setRegistrationResendCountdown(5);
      setRegistrationOtpEmail('');
      showMessage(data.email_sent === false ? 'error' : 'success', data.message || 'A verification code was sent to your work and personal email addresses.');
    } catch (error) {
      showMessage('error', error.message);
    } finally {
      setBusy(false);
    }
  };

  const resendLoginOtp = async () => {
    if (loginResendCountdown > 0 || busy) return;
    await submitLogin();
  };

  const resendRegistrationOtp = async () => {
    if (registrationResendCountdown > 0 || busy) return;
    await submitRegistration();
  };

  const verifyRegistration = async () => {
    clearMessage();
    if (registrationOtp.trim().length !== 6) {
      showMessage('error', 'Enter the 6-digit verification code.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/verify-registration`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: registration.phone_number.trim(), email: registrationOtpEmail.trim(), otp: registrationOtp.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Verification failed.'));
      setRegistrationOtpSent(false);
      setRegistrationOtp('');
      setAuthView('login');
      setLoginPhone(registration.phone_number);
      setLoginPassword('');
      showMessage('success', data.message || 'Registration verified. Your account is pending approval.');
    } catch (error) {
      showMessage('error', error.message);
    } finally {
      setBusy(false);
    }
  };

  const requestPasswordReset = async () => {
    clearMessage();
    if (!recoveryEmail.trim()) {
      showMessage('error', 'Enter the email address registered to your account.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/request-password-reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: recoveryEmail.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Unable to request a reset code.'));
      setResetOtpSent(true);
      setRecoveryOtpEmail('');
      showMessage(data.email_sent === false ? 'error' : 'success', data.message || 'A password reset code was sent to your registered email.');
    } catch (error) {
      showMessage('error', error.message);
    } finally {
      setBusy(false);
    }
  };

  const requestPhoneRecovery = async () => {
    clearMessage();
    if (!recoveryEmail.trim()) {
      showMessage('error', 'Enter the email address registered to your account.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/request-phone-recovery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: recoveryEmail.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Unable to request account recovery.'));
      setRecoveryOtpEmail('');
      setResetOtpSent(true);
      showMessage(data.email_sent === false ? 'error' : 'success', data.message || 'A recovery code was sent to your registered email.');
    } catch (error) {
      showMessage('error', error instanceof TypeError ? 'Cannot reach the authentication server.' : error.message);
    } finally {
      setBusy(false);
    }
  };

  const recoverPhone = async () => {
    clearMessage();
    if (resetOtp.trim().length !== 6 || !recoveryOtpEmail.trim()) {
      showMessage('error', 'Enter the 6-digit code and confirm the registered email address.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/recover-phone`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: recoveryOtpEmail.trim(), otp: resetOtp.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Unable to recover the phone number.'));
      setLoginPhone(data.phone_number);
      setResetOtpSent(false);
      showMessage('success', `Your registered phone number is ${data.phone_number}.`);
    } catch (error) {
      showMessage('error', error.message);
    } finally {
      setBusy(false);
    }
  };

  const resetPasswordRequest = async () => {
    clearMessage();
    if (resetOtp.trim().length !== 6 || resetPassword.length < 8 || !recoveryOtpEmail.trim()) {
      showMessage('error', 'Confirm the registered email, enter the 6-digit code, and choose a password of at least 8 characters.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${AUTH_API_BASE}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: recoveryOtpEmail.trim(), otp: resetOtp.trim(), new_password: resetPassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiError(data, 'Unable to reset password.'));
      setResetOtpSent(false);
      setAuthView('login');
      setLoginPassword('');
      showMessage('success', 'Password reset successfully. You can now sign in.');
    } catch (error) {
      showMessage('error', error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = async () => {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) {
        await fetch(`${AUTH_API_BASE}/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${refreshToken}` },
        });
      }
    } finally {
      clearAuthSession();
      setCurrentUser(null);
      setLoginOtpSent(false);
      setLoginOtp('');
      setAuthView('login');
      showMessage('success', 'You have been signed out.');
    }
  };

  if (currentUser) {
    const normalizedRole = String(currentUser.role || 'employee').toLowerCase();
    const roleLabel = normalizedRole === 'super_admin' || (normalizedRole === 'hr_admin' && currentUser.is_superuser === true)
      ? 'Super Admin Dashboard'
      : {
          employee: 'Employee Dashboard',
          manager: 'Manager Dashboard',
          hr_admin: 'Human Resources Dashboard',
          system_admin: 'System Admin Dashboard',
          super_admin: 'Super Admin Dashboard',
        }[normalizedRole] || 'Dashboard';

    return (
      <BrowserRouter>
        <>
        <div className="role-banner" style={{ padding: '0.75rem 1rem', background: '#edfdf8', borderBottom: '1px solid #d8f3eb', color: '#0f172a', fontWeight: 600 }}>
          {roleLabel}
        </div>
        <AuthenticatedRoutes currentUser={currentUser} onUserUpdated={(user) => setCurrentUser(normalizeUser(user))} handleLogout={handleLogout} />
        </>
      </BrowserRouter>
    );
  }

  const isRegistration = authView === 'register';
  const isReset = authView === 'reset';
  const isPhoneRecovery = authView === 'forgot-phone';
  const isOtp = isRegistration ? registrationOtpSent : isReset || isPhoneRecovery ? resetOtpSent : loginOtpSent;

  return (
    <div className="activation-container auth-page">
      <div className={`auth-card ${isRegistration ? 'registration-auth-card' : 'login-card'}`}>
        <aside className="auth-visual-panel">
          <p className="auth-visual-kicker">LEAVE, MADE SIMPLE</p>
          <h2>More time for the work that matters.</h2>
          <p>Request leave, track balances, and stay aligned with your team from one calm workspace.</p>
          <div className="auth-visual-rule" />
          <span>Secure employee access</span>
        </aside>
        <section className="auth-form-panel">
          <div className="auth-panel-logo"><img className="auth-logo" src="/Okoafloat.png" alt="Okoa Float" /></div>
          <div className="auth-form-heading">
            <span className="auth-eyebrow">EMPLOYEE PORTAL</span>
            <h1>{isRegistration ? 'Create your account' : isReset ? 'Reset your password' : isPhoneRecovery ? 'Recover your phone number' : isOtp ? 'Verify your identity' : 'Welcome back'}</h1>
            <p>{isRegistration ? 'Register to manage your leave.' : isReset || isPhoneRecovery ? 'A secure code will be sent to your registered email address.' : 'Sign in to manage your leave.'}</p>
          </div>

          {message && <div className={`login-${message.type === 'error' ? 'error' : 'success'}`} role="alert">{message.text}</div>}

          {isRegistration ? (
            registrationOtpSent ? (
              <>
                <EmailField value={registrationOtpEmail} onChange={setRegistrationOtpEmail} label="Confirm work or personal email" />
                <OtpForm value={registrationOtp} onChange={setRegistrationOtp} onSubmit={verifyRegistration} onResend={resendRegistrationOtp} resendCountdown={registrationResendCountdown} busy={busy} label="Enter email verification code" />
              </>
            ) : <RegistrationForm values={registration} setValues={setRegistration} onSubmit={submitRegistration} busy={busy} />
          ) : isReset ? (
            resetOtpSent ? (
              <>
                <EmailField value={recoveryOtpEmail} onChange={setRecoveryOtpEmail} label="Confirm work or personal email" />
                <div className="activation-input-group"><label>Enter reset code</label><input type="text" inputMode="numeric" maxLength={6} value={resetOtp} onChange={(event) => setResetOtp(event.target.value.replace(/\D/g, ''))} placeholder="_ _ _ _ _ _" className="activation-input otp-input" autoFocus /></div>
                <PasswordField value={resetPassword} onChange={setResetPassword} visible={showResetPassword} setVisible={setShowResetPassword} label="New password" />
                <div className="activation-actions"><button onClick={resetPasswordRequest} disabled={busy} className="btn-activate">{busy ? 'Resetting...' : 'Reset password'}</button></div>
              </>
            ) : <EmailField value={recoveryEmail} onChange={setRecoveryEmail} label="Work or personal email" onSubmit={requestPasswordReset} busy={busy} buttonLabel="Send reset code" />
          ) : isPhoneRecovery ? (
            resetOtpSent ? (
              <>
                <EmailField value={recoveryOtpEmail} onChange={setRecoveryOtpEmail} label="Confirm work or personal email" />
                <div className="activation-input-group"><label>Enter recovery code</label><input type="text" inputMode="numeric" maxLength={6} value={resetOtp} onChange={(event) => setResetOtp(event.target.value.replace(/\D/g, ''))} placeholder="_ _ _ _ _ _" className="activation-input otp-input" autoFocus /></div>
                <div className="activation-actions"><button onClick={recoverPhone} disabled={busy} className="btn-activate">{busy ? 'Verifying...' : 'Recover phone number'}</button></div>
              </>
            ) : <EmailField value={recoveryEmail} onChange={setRecoveryEmail} label="Work or personal email" onSubmit={requestPhoneRecovery} busy={busy} buttonLabel="Send recovery code" />
          ) : loginOtpSent ? (
            <>
              <div className="auth-otp-notice" role="status">
                <span className="auth-otp-notice-icon" aria-hidden="true"><Mail size={19} /></span>
                <div>
                  <strong>Check your email</strong>
                  <p>We sent a 6-digit sign-in code to the email address linked to <b>{loginPhone}</b>. Enter the code below to continue.</p>
                </div>
              </div>
              <OtpForm value={loginOtp} onChange={setLoginOtp} onSubmit={verifyLogin} onResend={resendLoginOtp} resendCountdown={loginResendCountdown} busy={busy} label="Enter 6-digit email code" />
            </>
          ) : (
            <>
              <PhoneForm value={loginPhone} onChange={setLoginPhone} label="Phone number" />
              <PasswordField value={loginPassword} onChange={setLoginPassword} visible={showLoginPassword} setVisible={setShowLoginPassword} label="Password" />
              <div className="activation-actions"><button onClick={submitLogin} disabled={busy} className="btn-activate">{busy ? 'Authenticating...' : 'Sign in'}</button></div>
              <div className="auth-links"><button onClick={() => { clearMessage(); setAuthView('reset'); setResetOtpSent(false); }} className="btn-resend-link">Forgot password?</button><button onClick={() => { clearMessage(); setAuthView('forgot-phone'); setResetOtpSent(false); }} className="btn-resend-link">Forgot phone number?</button><button onClick={() => { clearMessage(); setAuthView('register'); }} className="btn-resend-link">Register here</button></div>
            </>
          )}

          {(isOtp || isRegistration || isReset || isPhoneRecovery) && <div className="auth-links"><button className="btn-resend-link" onClick={() => { clearMessage(); setAuthView('login'); setLoginOtpSent(false); setRegistrationOtpSent(false); setResetOtpSent(false); setLoginOtp(''); setResetOtp(''); }}>Back to sign in</button></div>}
        </section>
      </div>
    </div>
  );
}

const PhoneForm = ({ value, onChange, onSubmit, busy, label, buttonLabel }) => (
  <div className="activation-input-group login-phone-group">
    <label>{label}</label>
    <input type="tel" autoComplete="tel" value={value} onChange={(event) => onChange(event.target.value)} placeholder="0712 345 678" className="activation-input" disabled={busy} onKeyDown={(event) => event.key === 'Enter' && onSubmit?.()} />
    {onSubmit && <div className="activation-actions"><button onClick={onSubmit} disabled={busy} className="btn-activate">{busy ? 'Please wait...' : buttonLabel}</button></div>}
  </div>
);

const EmailField = ({ value, onChange, label, onSubmit, busy, buttonLabel }) => (
  <div className="activation-input-group">
    <label>{label}</label>
    <input type="email" autoComplete="email" value={value} onChange={(event) => onChange(event.target.value)} placeholder="name@example.com" className="activation-input" disabled={busy} onKeyDown={(event) => event.key === 'Enter' && onSubmit?.()} />
    {onSubmit && <div className="activation-actions"><button onClick={onSubmit} disabled={busy} className="btn-activate">{busy ? 'Please wait...' : buttonLabel}</button></div>}
  </div>
);

const PasswordField = ({ value, onChange, visible, setVisible, label }) => (
  <div className="activation-input-group">
    <label>{label}</label>
    <div className="password-input-wrapper">
      <input type={visible ? 'text' : 'password'} autoComplete="new-password" value={value} onChange={(event) => onChange(event.target.value)} placeholder="Enter your password" className="activation-input" />
      <button type="button" className="password-toggle-btn text-toggle" aria-label={visible ? 'Hide password' : 'Show password'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button>
    </div>
  </div>
);

const OtpForm = ({ value, onChange, onSubmit, onResend, resendCountdown, busy, label }) => (
  <>
    <div className="activation-input-group"><label>{label}</label><input type="text" inputMode="numeric" maxLength={6} value={value} onChange={(event) => onChange(event.target.value.replace(/\D/g, ''))} placeholder="_ _ _ _ _ _" className="activation-input otp-input" autoFocus /></div>
    <div className="activation-actions"><button onClick={onSubmit} disabled={busy} className="btn-activate">{busy ? 'Verifying...' : 'Verify code'}</button></div>
    {onResend && <div className="auth-links otp-resend"><button type="button" className="btn-resend-link" onClick={onResend} disabled={busy || resendCountdown > 0}>{resendCountdown > 0 ? `Resend code in ${resendCountdown}s` : 'Resend code'}</button></div>}
  </>
);

const RegistrationForm = ({ values, setValues, onSubmit, busy }) => {
  const [showPassword, setShowPassword] = useState(false);

  return <>
    <div className="registration-form-grid">
      {[
      ['employee_name', 'Employee name', 'text'],
      ['job_position_title', 'Job position title', 'text'],
      ['employer', 'Employer', 'text'],
      ['department', 'Department', 'text'],
      ['email', 'Work email', 'email'],
      ['personal_email', 'Personal email', 'email'],
      ['phone_number', 'Phone number', 'tel'],
      ].map(([field, label, type]) => <div className="activation-input-group" key={field}><label>{label}</label><input type={type} value={values[field]} onChange={(event) => setValues({ ...values, [field]: event.target.value })} placeholder={label} className="activation-input" /></div>)}
      <PasswordField value={values.password} onChange={(password) => setValues({ ...values, password })} visible={showPassword} setVisible={setShowPassword} label="Password" />
    </div>
    <div className="activation-actions"><button onClick={onSubmit} disabled={busy} className="btn-activate">{busy ? 'Registering...' : 'Register'}</button></div>
  </>
};

export default App;
