import React, { useCallback, useEffect, useRef, useState } from 'react';
import { organizationApi } from '../services/organizationApi';

const requestPosition = () => new Promise((resolve, reject) => {
  if (!navigator.geolocation) {
    reject(new Error('This browser does not support location services.'));
    return;
  }
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => resolve({
      latitude: coords.latitude,
      longitude: coords.longitude,
      accuracy_meters: coords.accuracy,
    }),
    (error) => reject(new Error(error.code === error.PERMISSION_DENIED
      ? 'Location permission was denied. Allow location access to start this visit.'
      : error.code === error.TIMEOUT
        ? 'Location lookup timed out. Check your signal and try again.'
        : 'Unable to read your current location.')),
    { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 },
  );
});

export default function ActiveFieldVisitLocation({ enabled, endSignal = 0 }) {
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const activeRef = useRef(false);
  const stopPromise = useRef(null);

  const sendPosition = useCallback(async () => {
    if (!activeRef.current || document.visibilityState === 'hidden') return;
    try {
      const position = await requestPosition();
      if (!activeRef.current || document.visibilityState === 'hidden') return;
      await organizationApi.pingLocation(position, undefined, 'active_visit');
      setMessage(`Visit location shared at ${new Date().toLocaleTimeString()}.`);
      setError('');
    } catch (requestError) {
      if (requestError.status === 429) {
        setMessage('Visit is active. The next location update will be sent after the rate limit.');
        return;
      }
      if (activeRef.current) setError(requestError.message || 'Unable to share this visit location.');
    }
  }, []);

  const stop = useCallback(async (keepalive = false) => {
    if (!activeRef.current || stopPromise.current) return stopPromise.current;
    activeRef.current = false;
    setActive(false);
    stopPromise.current = organizationApi.setActiveFieldVisit('stop', { keepalive })
      .then(() => setMessage('Field visit ended. Location sharing is off.'))
      .catch((requestError) => setError(
        `Visit sharing stopped in this browser, but the server could not confirm stop: ${requestError.message}`,
      ))
      .finally(() => { stopPromise.current = null; });
    return stopPromise.current;
  }, []);

  const start = async () => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      // This call is made directly from the agent's click, so the browser
      // permission prompt is explicit and never invoked by a background timer.
      const position = await requestPosition();
      await organizationApi.setActiveFieldVisit('start');
      activeRef.current = true;
      setActive(true);
      setMessage('Active field visit. Location sharing is visible to your permitted supervisors.');
      try {
        await organizationApi.pingLocation(position, undefined, 'active_visit');
        setMessage(`Visit location shared at ${new Date().toLocaleTimeString()}.`);
      } catch (requestError) {
        if (requestError.status === 429) {
          setMessage('Visit is active. The next location update will be sent after the rate limit.');
        } else {
          throw requestError;
        }
      }
    } catch (requestError) {
      if (activeRef.current) await stop();
      setError(requestError.message || 'Unable to start location sharing.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!enabled && activeRef.current) stop();
  }, [enabled, stop]);

  useEffect(() => {
    if (endSignal > 0 && activeRef.current) stop();
  }, [endSignal, stop]);

  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(sendPosition, 60000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') sendPosition();
    };
    const onPageHide = () => { stop(true); };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', onPageHide);
      if (activeRef.current) stop(true);
    };
  }, [active, sendPosition, stop]);

  if (!enabled) return null;
  return (
    <aside className="sales-active-visit-location" aria-label="Field visit location sharing">
      <p><strong>{active ? 'Location sharing is ON' : 'Location sharing is OFF'}</strong></p>
      <p>Optional: start sharing only while this field visit is active. Your browser will ask for location permission. Sharing stops when you end the visit; leaving the page sends a stop request, and an offline session expires within eight hours. No phone-number tracking or background GPS is used.</p>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {active
        ? <button type="button" className="leave-secondary-button" onClick={() => stop()} disabled={busy}>End visit and stop sharing</button>
        : <button type="button" className="leave-secondary-button" onClick={start} disabled={busy}>
          {busy ? 'Requesting location…' : 'Start field visit and opt in to location'}
        </button>}
    </aside>
  );
}
