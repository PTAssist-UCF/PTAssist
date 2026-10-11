import { useState, useEffect } from 'react';

function AccessibilityPanel() {
  const [open, setOpen] = useState(false);
  const [fontSize, setFontSize] = useState(100);
  const [highContrast, setHighContrast] = useState(false);
  const [screenReader, setScreenReader] = useState(false);

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontSize}%`;
    if (highContrast) {
      document.documentElement.setAttribute('data-hc', '1');
      document.documentElement.style.filter = 'contrast(1.4)';
    } else {
      document.documentElement.removeAttribute('data-hc');
      document.documentElement.style.filter = '';
    }
  }, [fontSize, highContrast]);

  function toggleScreenReader() {
    const next = !screenReader;
    setScreenReader(next);
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const msg = new SpeechSynthesisUtterance(
        next
          ? 'Screen reader enabled. Focused elements will be read aloud.'
          : 'Screen reader disabled.',
      );
      msg.rate = 0.9;
      msg.pitch = 1;
      window.speechSynthesis.speak(msg);
    }
    if (next) {
      document.addEventListener('focusin', speakFocused);
    } else {
      document.removeEventListener('focusin', speakFocused);
    }
  }

  function speakFocused(e: Event) {
    const el = e.target as HTMLElement;
    const text =
      el.getAttribute('aria-label') ||
      (el as HTMLInputElement).placeholder ||
      el.textContent?.trim() ||
      el.tagName.toLowerCase();
    if (text && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const msg = new SpeechSynthesisUtterance(text);
      msg.rate = 0.9;
      window.speechSynthesis.speak(msg);
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {open && (
        <div
          className="rounded-2xl shadow-2xl p-5 w-72 flex flex-col gap-5"
          style={{ background: '#fff', border: '2px solid #0d9488' }}
        >
          <h2 className="text-xl font-800" style={{ color: '#1e3a5f' }}>
            Accessibility
          </h2>

          {/* Text size */}
          <div className="flex flex-col gap-2">
            <span className="text-base font-700" style={{ color: '#1e3a5f' }}>
              Text Size
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setFontSize((s) => Math.max(80, s - 10))}
                className="w-10 h-10 rounded-xl text-2xl font-800 flex items-center justify-center transition-opacity hover:opacity-70"
                style={{ background: '#e8f7f6', color: '#0d9488' }}
                aria-label="Decrease text size"
              >
                A−
              </button>
              <span className="flex-1 text-center text-base font-600" style={{ color: '#4a7fa0' }}>
                {fontSize}%
              </span>
              <button
                onClick={() => setFontSize((s) => Math.min(150, s + 10))}
                className="w-10 h-10 rounded-xl text-2xl font-800 flex items-center justify-center transition-opacity hover:opacity-70"
                style={{ background: '#e8f7f6', color: '#0d9488' }}
                aria-label="Increase text size"
              >
                A+
              </button>
            </div>
          </div>

          {/* High contrast */}
          <div className="flex items-center justify-between">
            <span className="text-base font-700" style={{ color: '#1e3a5f' }}>
              High Contrast
            </span>
            <button
              role="switch"
              aria-checked={highContrast}
              onClick={() => setHighContrast((v) => !v)}
              className="relative w-14 h-8 rounded-full transition-all"
              style={{ background: highContrast ? '#0d9488' : '#ccf0f0' }}
            >
              <span
                className="absolute top-1 left-1 w-6 h-6 rounded-full bg-white shadow transition-transform"
                style={{ transform: highContrast ? 'translateX(24px)' : 'translateX(0)' }}
              />
            </button>
          </div>

          {/* Screen reader */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-base font-700" style={{ color: '#1e3a5f' }}>
                  Screen Reader
                </span>
                <span className="text-sm font-500" style={{ color: '#7ab8c8' }}>
                  Reads focused items aloud
                </span>
              </div>
              <button
                role="switch"
                aria-checked={screenReader}
                onClick={toggleScreenReader}
                aria-label="Toggle screen reader"
                className="relative w-14 h-8 rounded-full transition-all flex-shrink-0"
                style={{ background: screenReader ? '#0d9488' : '#ccf0f0' }}
              >
                <span
                  className="absolute top-1 left-1 w-6 h-6 rounded-full bg-white shadow transition-transform"
                  style={{ transform: screenReader ? 'translateX(24px)' : 'translateX(0)' }}
                />
              </button>
            </div>
            {screenReader && (
              <p
                className="text-sm font-600 rounded-lg px-3 py-2"
                style={{ background: '#e8f7f6', color: '#115e59' }}
              >
                Active — tap any field or button to hear it read aloud.
              </p>
            )}
          </div>

          {/* Reset */}
          <button
            onClick={() => {
              setFontSize(100);
              setHighContrast(false);
              if (screenReader) toggleScreenReader();
            }}
            className="w-full rounded-xl py-2 text-base font-700 transition-opacity hover:opacity-70"
            style={{ background: '#f0fafa', color: '#0d9488', border: '1.5px solid #0d9488' }}
          >
            Reset to Default
          </button>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open accessibility options"
        className="w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        style={{ background: '#0d9488' }}
      >
        <svg viewBox="0 0 24 24" fill="none" className="w-7 h-7" stroke="white" strokeWidth="2">
          <circle cx="12" cy="4" r="1.5" fill="white" stroke="none" />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 7v5m0 0l-3 4m3-4l3 4M9 10H6m12 0h-3"
          />
        </svg>
      </button>
    </div>
  );
}

export default function PatientLoginMock() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showReset, setShowReset] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetSent, setResetSent] = useState(false);

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    // login logic placeholder
  }

  function handleReset(e: React.FormEvent) {
    e.preventDefault();
    setResetSent(true);
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6 py-12"
      style={{ background: 'linear-gradient(160deg, #e8f7f6 0%, #f0fafa 50%, #e2f0fb 100%)' }}
    >
      {/* Logo / Brand mark */}
      <div className="mb-8 flex flex-col items-center gap-2">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center shadow-md"
          style={{ background: '#0d9488' }}
        >
          <svg viewBox="0 0 32 32" fill="none" className="w-9 h-9">
            <path
              d="M16 6C10.477 6 6 10.477 6 16s4.477 10 10 10 10-4.477 10-10S21.523 6 16 6zm0 4a3 3 0 110 6 3 3 0 010-6zm0 13.5c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"
              fill="white"
              fillOpacity="0.95"
            />
          </svg>
        </div>
        <span className="text-lg font-700 tracking-wide" style={{ color: '#115e59' }}>
          PTAssist
        </span>
      </div>

      {/* Card */}
      <div
        className="w-full max-w-md bg-white rounded-3xl shadow-xl px-8 py-10"
        style={{ border: '1.5px solid #ccf0f0' }}
      >
        {!showReset ? (
          <>
            {/* Header */}
            <div className="mb-8 text-center">
              <h1 className="text-4xl font-800 mb-2" style={{ color: '#1e3a5f' }}>
                Patient Login
              </h1>
              <p className="text-lg font-500" style={{ color: '#4a7fa0' }}>
                Welcome back. Please sign in below.
              </p>
            </div>

            {/* Form */}
            <form onSubmit={handleLogin} className="flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <label htmlFor="email" className="text-xl font-700" style={{ color: '#1e3a5f' }}>
                  Email or Username
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="w-full rounded-xl px-5 py-4 text-xl font-500 outline-none transition-all"
                  style={{
                    border: '2px solid #ccf0f0',
                    background: '#f8fffe',
                    color: '#1e3a5f',
                    fontSize: '1.2rem',
                  }}
                  onFocus={(e) => (e.currentTarget.style.border = '2px solid #0d9488')}
                  onBlur={(e) => (e.currentTarget.style.border = '2px solid #ccf0f0')}
                />
              </div>

              <div className="flex flex-col gap-2">
                <label htmlFor="password" className="text-xl font-700" style={{ color: '#1e3a5f' }}>
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  className="w-full rounded-xl px-5 py-4 text-xl font-500 outline-none transition-all"
                  style={{
                    border: '2px solid #ccf0f0',
                    background: '#f8fffe',
                    color: '#1e3a5f',
                    fontSize: '1.2rem',
                  }}
                  onFocus={(e) => (e.currentTarget.style.border = '2px solid #0d9488')}
                  onBlur={(e) => (e.currentTarget.style.border = '2px solid #ccf0f0')}
                />
              </div>

              {/* Reset link */}
              <div className="text-right -mt-2">
                <button
                  type="button"
                  onClick={() => setShowReset(true)}
                  className="text-lg font-600 underline underline-offset-2 transition-opacity hover:opacity-70"
                  style={{ color: '#0d9488' }}
                >
                  Forgot your password?
                </button>
              </div>

              {/* Sign in button */}
              <button
                type="submit"
                className="w-full rounded-xl py-5 text-2xl font-800 text-white transition-all hover:opacity-90 active:scale-98 shadow-md mt-2"
                style={{ background: '#0d9488', letterSpacing: '0.01em' }}
              >
                Sign In
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center gap-4 my-8">
              <div className="flex-1 h-px" style={{ background: '#ccf0f0' }} />
              <span className="text-base font-600" style={{ color: '#7ab8c8' }}>
                OR
              </span>
              <div className="flex-1 h-px" style={{ background: '#ccf0f0' }} />
            </div>

            {/* Switch to therapist */}
            <a
              href="#"
              onClick={(e) => e.preventDefault()}
              className="flex items-center justify-center gap-3 w-full rounded-xl py-4 text-xl font-700 transition-all hover:opacity-80"
              style={{
                border: '2px solid #0d9488',
                color: '#0d9488',
                background: 'transparent',
              }}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="w-6 h-6"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
              Sign up with patient code
            </a>
          </>
        ) : (
          /* Reset password view */
          <>
            <button
              type="button"
              onClick={() => {
                setShowReset(false);
                setResetSent(false);
                setResetEmail('');
              }}
              className="flex items-center gap-2 mb-6 text-lg font-600 transition-opacity hover:opacity-70"
              style={{ color: '#0d9488' }}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="w-5 h-5"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
              Back to Login
            </button>

            <div className="mb-8 text-center">
              <h1 className="text-4xl font-800 mb-2" style={{ color: '#1e3a5f' }}>
                Reset Password
              </h1>
              <p className="text-lg font-500" style={{ color: '#4a7fa0' }}>
                We'll send a reset link to your email.
              </p>
            </div>

            {!resetSent ? (
              <form onSubmit={handleReset} className="flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <label
                    htmlFor="reset-email"
                    className="text-xl font-700"
                    style={{ color: '#1e3a5f' }}
                  >
                    Your Email Address
                  </label>
                  <input
                    id="reset-email"
                    type="email"
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    placeholder="you@example.com"
                    required
                    className="w-full rounded-xl px-5 py-4 text-xl font-500 outline-none transition-all"
                    style={{
                      border: '2px solid #ccf0f0',
                      background: '#f8fffe',
                      color: '#1e3a5f',
                      fontSize: '1.2rem',
                    }}
                    onFocus={(e) => (e.currentTarget.style.border = '2px solid #0d9488')}
                    onBlur={(e) => (e.currentTarget.style.border = '2px solid #ccf0f0')}
                  />
                </div>
                <button
                  type="submit"
                  className="w-full rounded-xl py-5 text-2xl font-800 text-white transition-all hover:opacity-90 shadow-md mt-2"
                  style={{ background: '#0d9488' }}
                >
                  Send Reset Link
                </button>
              </form>
            ) : (
              <div
                className="rounded-2xl p-6 text-center"
                style={{ background: '#e8f7f6', border: '2px solid #0d9488' }}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  className="w-12 h-12 mx-auto mb-3"
                  stroke="#0d9488"
                  strokeWidth="2"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="text-xl font-700" style={{ color: '#115e59' }}>
                  Check your inbox!
                </p>
                <p className="text-lg font-500 mt-1" style={{ color: '#4a7fa0' }}>
                  A reset link has been sent to <strong>{resetEmail}</strong>
                </p>
              </div>
            )}
          </>
        )}
      </div>

      <AccessibilityPanel />
    </div>
  );
}
