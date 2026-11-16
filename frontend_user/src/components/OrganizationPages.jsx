import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { organizationApi } from '../services/organizationApi';
import SalesDailyReportForm from './SalesDailyReportForm';
import './OrganizationPages.css';

const pageStyle = { display: 'grid', gap: 16, maxWidth: 980, margin: '0 auto', padding: 20 };
const cardStyle = { background: 'var(--card-bg, #fff)', border: '1px solid #e8e2dc', borderRadius: 12, padding: 18 };
const errorText = { color: '#b46118' };
const asLocalDateTimeInput = (date) => {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 16);
};

export const ActiveAssignmentGuard = ({ roles, organizationalRole, children }) => {
  const [assignment, setAssignment] = useState(undefined);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    organizationApi.getMyAssignment()
      .then((value) => { if (active) setAssignment(value); })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message);
          setAssignment(null);
        }
      });
    return () => { active = false; };
  }, []);

  if (assignment === undefined) return <p role="status">Checking active department access…</p>;
  if (
    error
    || !assignment
    || !roles.includes(assignment.department_role)
    || (organizationalRole && assignment.organizational_role !== organizationalRole)
  ) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
};

const statusEvent = (status, error = '') => {
  window.dispatchEvent(new CustomEvent('okoa-location-status', { detail: { status, error } }));
};

const requestCurrentPosition = () => new Promise((resolve, reject) => {
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
    (error) => {
      const message = error.code === error.PERMISSION_DENIED
        ? 'Location permission was denied. Enable location access in your browser to continue.'
        : error.code === error.TIMEOUT
          ? 'Location lookup timed out. Check your signal and try again.'
          : 'Unable to read your current location.';
      reject(new Error(message));
    },
    { enableHighAccuracy: true, maximumAge: 30000, timeout: 20000 },
  );
});

export const AgentLocationTracker = ({ isFieldAgent = false }) => {
  const [trackingStatus, setTrackingStatus] = useState('');
  const [trackingError, setTrackingError] = useState('');

  useEffect(() => {
    if (!isFieldAgent) {
      window.sessionStorage.removeItem('okoa_location_tracking');
      setTrackingStatus('');
      setTrackingError('');
      return undefined;
    }

    let active = true;
    let inFlight = false;
    const controller = new AbortController();
    const syncAndPing = async () => {
      if (!active || inFlight || document.visibilityState === 'hidden') return;
      inFlight = true;
      try {
        const tracking = await organizationApi.getAgentLocationTrackingStatus();
        if (!active) return;
        if (!tracking.enabled) {
          window.sessionStorage.removeItem('okoa_location_tracking');
          setTrackingStatus('Location tracking is outside its scheduled hours.');
          setTrackingError('');
          return;
        }
        window.sessionStorage.setItem('okoa_location_tracking', 'enabled');
        setTrackingStatus('Location tracking is active during the administrator schedule.');
        setTrackingError('');
        const lastPingAt = Number(window.sessionStorage.getItem('okoa_location_last_ping') || 0);
        if (Date.now() - lastPingAt < 60000) return;
        const coordinates = await requestCurrentPosition();
        if (!active) return;
        await organizationApi.pingLocation(coordinates, controller.signal);
        if (!active) return;
        window.sessionStorage.setItem('okoa_location_last_ping', String(Date.now()));
        setTrackingStatus(`Location updated at ${new Date().toLocaleTimeString()}.`);
        statusEvent('tracking');
      } catch (error) {
        if (active && error.name !== 'AbortError') {
          if (error.code === 'LOCATION_TRACKING_DISABLED') {
            setTrackingStatus('Location tracking is outside its scheduled hours.');
            setTrackingError('');
          } else {
            setTrackingError(error.message);
            statusEvent('error', error.message);
          }
        }
      } finally {
        inFlight = false;
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') syncAndPing();
    };
    syncAndPing();
    const timer = window.setInterval(syncAndPing, 60000);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [isFieldAgent]);

  if (!isFieldAgent || (!trackingStatus && !trackingError)) return null;
  return (
    <p
      className={`agent-tracking-notice${trackingError ? ' has-error' : ''}`}
      role={trackingError ? 'alert' : 'status'}
    >
      {trackingError || trackingStatus}
    </p>
  );
};

const trackingDays = [
  ['mon', 'Monday'],
  ['tue', 'Tuesday'],
  ['wed', 'Wednesday'],
  ['thu', 'Thursday'],
  ['fri', 'Friday'],
  ['sat', 'Saturday'],
  ['sun', 'Sunday'],
];

export const LocationTrackingScheduleSettings = () => {
  const [schedule, setSchedule] = useState({
    enabled: false,
    timezone: 'Africa/Nairobi',
    days: [],
    start_time: '08:00',
    end_time: '17:00',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    organizationApi.getLocationTrackingSchedule()
      .then((value) => {
        if (active) setSchedule(value);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const saveSchedule = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await organizationApi.setLocationTrackingSchedule(schedule);
      setSchedule(saved);
      setMessage('Tracking schedule saved. Existing manager overrides have been reset.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleDay = (day) => {
    setSchedule((current) => ({
      ...current,
      days: current.days.includes(day)
        ? current.days.filter((value) => value !== day)
        : trackingDays
          .map(([value]) => value)
          .filter((value) => current.days.includes(value) || value === day),
    }));
  };

  return (
    <section className="admin-card location-schedule-settings" aria-labelledby="location-schedule-title">
      <div className="leave-section-heading">
        <div>
          <p className="leave-kicker">FIELD OPERATIONS</p>
          <h2 id="location-schedule-title">Agent live-tracking schedule</h2>
        </div>
        <span className={`location-schedule-state${schedule.enabled ? ' is-enabled' : ''}`}>
          {schedule.enabled ? 'Schedule enabled' : 'Tracking off'}
        </span>
      </div>
      <p>
        Location collection runs automatically for active field agents during these recurring hours.
        GPS permission and an open, visible app are required. Times use Africa/Nairobi.
      </p>
      {loading && <p role="status">Loading schedule…</p>}
      {error && <p className="leave-alert error" role="alert">{error}</p>}
      <form className="admin-form" onSubmit={saveSchedule}>
        <label className="location-schedule-enable">
          <input
            type="checkbox"
            checked={schedule.enabled}
            onChange={(event) => setSchedule((current) => ({
              ...current,
              enabled: event.target.checked,
            }))}
            disabled={loading || saving}
          />
          Enable automatic tracking during the schedule
        </label>
        <fieldset className="location-schedule-days" disabled={loading || saving || !schedule.enabled}>
          <legend>Days of the week</legend>
          {trackingDays.map(([day, label]) => (
            <label key={day}>
              <input
                type="checkbox"
                checked={schedule.days.includes(day)}
                onChange={() => toggleDay(day)}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <div className="leave-form-row">
          <label>
            Start time (Africa/Nairobi)
            <input
              type="time"
              value={schedule.start_time}
              onChange={(event) => setSchedule((current) => ({
                ...current,
                start_time: event.target.value,
              }))}
              disabled={loading || saving || !schedule.enabled}
              required
            />
          </label>
          <label>
            End time (Africa/Nairobi)
            <input
              type="time"
              value={schedule.end_time}
              onChange={(event) => setSchedule((current) => ({
                ...current,
                end_time: event.target.value,
              }))}
              disabled={loading || saving || !schedule.enabled}
              required
            />
          </label>
        </div>
        <p>Use different start and end times; overnight hours are supported.</p>
        {message && <p className="location-schedule-success" role="status">{message}</p>}
        <div className="leave-modal-actions">
          <button type="submit" className="leave-primary-button" disabled={loading || saving}>
            {saving ? 'Saving…' : 'Save tracking schedule'}
          </button>
        </div>
      </form>
    </section>
  );
};

export const LocationSharingAdminPanel = () => {
  const [agents, setAgents] = useState([]);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const result = await organizationApi.getLiveLocations();
        if (active) {
          setAgents(result.agents || []);
          setUpdatedAt(result.refreshed_at || '');
          setError('');
        }
      } catch (requestError) {
        if (active) setError(requestError.message);
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const statusLabel = (agent) => {
    if (agent.active_visit) {
      return agent.sharing_status === 'on'
        ? 'Active field visit · sharing now'
        : 'Active field visit · awaiting location';
    }
    if (agent.sharing_status === 'on') return 'Tracking now';
    if (agent.sharing_status === 'stale') return 'Scheduled · awaiting location';
    if (agent.override_active && agent.scheduled_enabled) return 'Paused by manager';
    return 'Outside schedule';
  };
  const sharingNow = agents.filter((agent) => agent.sharing_status === 'on').length;

  return (
    <section className="location-sharing-admin-panel" style={cardStyle} aria-labelledby="location-sharing-status-title">
      <h2 id="location-sharing-status-title">Staff live-tracking status</h2>
      <p>
        {sharingNow} tracking now · {agents.length - sharingNow} outside schedule or without a recent update.
        {updatedAt ? ` Updated ${new Date(updatedAt).toLocaleTimeString()}.` : ''}
      </p>
      {error && <p style={errorText} role="alert">{error}</p>}
      {!error && agents.length === 0 && <p>No active field agents are currently assigned.</p>}
      {!error && agents.length > 0 && sharingNow === 0 && <p>No field agents are currently sharing a recent live location.</p>}
      {agents.length > 0 && (
        <div className="location-sharing-admin-table-wrap">
          <table className="location-sharing-admin-table">
            <thead><tr><th>Employee</th><th>Department</th><th>Tracking</th><th>Last location update</th></tr></thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.user_id}>
                  <td>{agent.name}</td>
                  <td>{agent.department || 'Unassigned'}</td>
                  <td>
                    <span className={`location-sharing-status-chip${agent.sharing_status === 'on' ? ' is-on' : agent.sharing_status === 'stale' || agent.active_visit ? ' is-stale' : ''}`}>
                      {statusLabel(agent)}
                    </span>
                  </td>
                  <td>{agent.last_ping_at ? new Date(agent.last_ping_at).toLocaleString() : 'No update in the last 24 hours'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>Statuses refresh every 30 seconds. Location history is available only to authorized managers and is retained for up to 30 days.</p>
    </section>
  );
};

export const ClientRegistrationPage = () => {
  const [addingClient, setAddingClient] = useState(false);

  if (addingClient) return <SalesDailyReportForm />;

  return (
    <main style={pageStyle}>
      <header>
        <h1>Sales report</h1>
        <p>Record a new or existing M-Pesa client interaction.</p>
      </header>
      <section style={cardStyle}>
        <button type="button" onClick={() => setAddingClient(true)}>
          Add New Client
        </button>
      </section>
    </main>
  );
};

export const HistoricalReportsPage = () => {
  const [reports, setReports] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const loadReports = useCallback(async () => {
    try {
      setReports(await organizationApi.getHistoricalReports());
      setError('');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadReports(); }, [loadReports]);

  return (
    <main style={pageStyle}>
      <header>
        <h1>Previous department reports</h1>
        <p>Reports from previous assignments are available for review only.</p>
      </header>
      {error && <p style={errorText} role="alert">{error}</p>}
      {loading && <p>Loading report history…</p>}
      {!loading && reports.length === 0 && <p>No reports from previous departments were found.</p>}
      {reports.map((report) => (
        <article style={cardStyle} key={report.id}>
          <h2>{report.business_owner_name || report.agent_name || 'Sales report'}</h2>
          <p>{report.department} · {report.date_visited} · {report.outcome}</p>
          <p>{report.notes || 'No additional notes.'}</p>
          <button type="button" disabled aria-disabled="true">Read-only — editing and submission are disabled</button>
        </article>
      ))}
    </main>
  );
};

export const DepartmentTransferPage = ({ currentUser }) => {
  const [departments, setDepartments] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [employeeId, setEmployeeId] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [position, setPosition] = useState('field_agent');
  const [managerId, setManagerId] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      organizationApi.getDepartments(),
      organizationApi.getTransferCandidates(),
    ])
      .then(([departmentRows, employeeRows]) => {
        if (!active) return;
        setDepartments(departmentRows || []);
        setEmployees(employeeRows || []);
      })
      .catch((requestError) => { if (active) setError(requestError.message); });
    return () => { active = false; };
  }, [currentUser?.id]);

  const selectedDepartment = departments.find((department) => String(department.id) === departmentId);
  const selectedEmployee = employees.find((employee) => String(employee.id) === employeeId);
  const transferTargets = employees.filter((employee) => employee.id !== currentUser?.id);
  const departmentName = String(selectedDepartment?.name || '').toLowerCase();
  const departmentRole = departmentName.includes('sales') || departmentName.includes('marketing')
    ? 'sales'
    : departmentName.includes('debt')
      ? 'debt_collection'
      : departmentName.includes('care')
        ? 'customer_care'
        : '';
  const managerPosition = {
    department_manager: 'general_manager',
    team_leader: 'department_manager',
    field_agent: 'team_leader',
  }[position];
  const managers = employees.filter((employee) => (
    employee.organizational_role === managerPosition
    && (
      position === 'department_manager'
      || employee.department_id === Number(departmentId)
    )
  ));

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');
    if (!selectedEmployee || !selectedDepartment) {
      setError('Select an employee and a destination department.');
      return;
    }
    if (position === 'field_agent' && !departmentRole) {
      setError('Field agents can only be assigned to a configured operational department.');
      return;
    }
    if (position !== 'general_manager' && !managerId) {
      setError('Select the employee’s manager in the reporting hierarchy.');
      return;
    }
    setBusy(true);
    try {
      await organizationApi.transferEmployee(selectedEmployee.id, {
        department_id: selectedDepartment.id,
        department_role: departmentRole || null,
        organizational_role: position,
        manager_id: managerId || null,
      });
      setMessage(`${selectedEmployee.name} was transferred to ${selectedDepartment.name}. Previous department write access was revoked.`);
      setEmployeeId('');
      setManagerId('');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={pageStyle}>
      <header>
        <h1>Department transfers</h1>
        <p>Transfers update department, operational role, reporting line, and history together.</p>
      </header>
      <form style={cardStyle} onSubmit={submit}>
        <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}>
          Employee
          <select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} required>
            <option value="">Select employee</option>
            {transferTargets.map((employee) => (
              <option key={employee.id} value={employee.id}>
                {employee.name} — {employee.department || 'Unassigned'}
              </option>
            ))}
          </select>
        </label>
        {selectedEmployee && <p>Current assignment: {selectedEmployee.organizational_role.replace(/_/g, ' ')} · {selectedEmployee.department_role || 'no operational role'}</p>}
        <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}>
          Destination department
          <select value={departmentId} onChange={(event) => { setDepartmentId(event.target.value); setManagerId(''); }} required>
            <option value="">Select department</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>{department.name}</option>
            ))}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}>
          Organizational role
          <select value={position} onChange={(event) => { setPosition(event.target.value); setManagerId(''); }}>
            <option value="field_agent">Field Agent</option>
            <option value="team_leader">Team Leader</option>
            <option value="department_manager">Department Manager</option>
            <option value="general_manager">General Manager</option>
          </select>
        </label>
        {position !== 'general_manager' && (
          <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}>
            Reporting manager
            <select value={managerId} onChange={(event) => setManagerId(event.target.value)} required>
              <option value="">Select manager</option>
              {managers.map((manager) => (
                <option key={manager.id} value={manager.id}>{manager.name} — {manager.organizational_role.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </label>
        )}
        {error && <p role="alert" style={errorText}>{error}</p>}
        {message && <p role="status">{message}</p>}
        <button type="submit" disabled={busy || !departments.length || !transferTargets.length}>
          {busy ? 'Saving transfer…' : 'Confirm transfer'}
        </button>
      </form>
    </main>
  );
};

const FitMapToLocations = ({ points }) => {
  const map = useMap();

  useEffect(() => {
    const distinctPoints = [...new Map(points.map((point) => [point.join(','), point])).values()];
    if (distinctPoints.length === 1) {
      map.setView(points[0], 15);
    } else if (distinctPoints.length > 1) {
      map.fitBounds(distinctPoints, { padding: [24, 24], maxZoom: 16 });
    }
  }, [map, points]);

  return null;
};

const LocationMap = ({ points, center, zoom = 13, children, label, fitPoints = true }) => (
  <MapContainer
    center={center}
    zoom={zoom}
    scrollWheelZoom
    style={{ width: '100%', height: 420, borderRadius: 10, zIndex: 0 }}
    aria-label={label}
  >
    <TileLayer
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    />
    {fitPoints && <FitMapToLocations points={points} />}
    {children}
  </MapContainer>
);

const LocationTrailPlayback = ({ points, name, agentId }) => {
  const orderedPoints = useMemo(
    () => [...points].sort(
      (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime(),
    ),
    [points],
  );
  const firstTime = orderedPoints.length
    ? new Date(orderedPoints[0].recorded_at).getTime()
    : 0;
  const lastTime = orderedPoints.length
    ? new Date(orderedPoints[orderedPoints.length - 1].recorded_at).getTime()
    : 0;
  const routePositions = useMemo(
    () => orderedPoints.map((point) => [point.latitude, point.longitude]),
    [orderedPoints],
  );
  const [currentTime, setCurrentTime] = useState(firstTime);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    setCurrentTime(firstTime);
    setPlaying(false);
  }, [firstTime, lastTime, points]);

  useEffect(() => {
    if (!playing || orderedPoints.length < 2 || currentTime >= lastTime) {
      if (currentTime >= lastTime) setPlaying(false);
      return undefined;
    }
    const timer = window.setInterval(
      () => setCurrentTime((time) => Math.min(lastTime, time + 250 * speed)),
      250,
    );
    return () => window.clearInterval(timer);
  }, [currentTime, lastTime, orderedPoints.length, playing, speed]);

  if (orderedPoints.length === 0) return <p>No location history is available for this period.</p>;

  let previousPoint = orderedPoints[0];
  let nextPoint = orderedPoints[orderedPoints.length - 1];
  for (let index = 1; index < orderedPoints.length; index += 1) {
    if (new Date(orderedPoints[index].recorded_at).getTime() >= currentTime) {
      previousPoint = orderedPoints[index - 1];
      nextPoint = orderedPoints[index];
      break;
    }
  }
  const previousTime = new Date(previousPoint.recorded_at).getTime();
  const nextTime = new Date(nextPoint.recorded_at).getTime();
  const interpolation = nextTime === previousTime
    ? 0
    : Math.max(0, Math.min(1, (currentTime - previousTime) / (nextTime - previousTime)));
  const activePoint = {
    ...previousPoint,
    latitude: previousPoint.latitude
      + (nextPoint.latitude - previousPoint.latitude) * interpolation,
    longitude: previousPoint.longitude
      + (nextPoint.longitude - previousPoint.longitude) * interpolation,
    recorded_at: new Date(currentTime).toISOString(),
    is_simulated: previousPoint.is_simulated || nextPoint.is_simulated,
  };
  const completedRoute = orderedPoints
    .filter((point) => new Date(point.recorded_at).getTime() <= currentTime)
    .map((point) => [point.latitude, point.longitude]);
  completedRoute.push([activePoint.latitude, activePoint.longitude]);

  const seek = (offset) => {
    setPlaying(false);
    setCurrentTime((time) => Math.max(firstTime, Math.min(lastTime, time + offset)));
  };

  return (
    <div>
      <LocationMap
        points={routePositions}
        center={routePositions[0]}
        label={`${name} historical location playback`}
      >
        <Polyline positions={routePositions} pathOptions={{ color: '#857466', weight: 4, opacity: 0.55 }} />
        <Polyline positions={completedRoute} pathOptions={{ color: '#874b17', weight: 5 }} />
        <CircleMarker
          center={[activePoint.latitude, activePoint.longitude]}
          radius={9}
          pathOptions={{
            color: activePoint.is_simulated ? '#783a12' : '#783a12',
            fillColor: activePoint.is_simulated ? '#f2780e' : '#e9740e',
            fillOpacity: 1,
          }}
        >
          <Popup>{name} · {activePoint.is_simulated ? 'Demo data — not live GPS' : 'Playback position'}</Popup>
        </CircleMarker>
      </LocationMap>
      <p aria-live="polite">
        {new Date(currentTime).toLocaleString()}
        {' · '}{activePoint.latitude.toFixed(5)}, {activePoint.longitude.toFixed(5)}
        {activePoint.accuracy_meters ? ` · ±${Math.round(activePoint.accuracy_meters)} m` : ''}
      </p>
      {activePoint.is_simulated && (
        <p role="note"><strong>Demo data — not live GPS.</strong></p>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <button type="button" onClick={() => seek(-60000)} disabled={currentTime <= firstTime}>Rewind 1 minute</button>
        <button
          type="button"
          onClick={() => {
            if (currentTime >= lastTime) setCurrentTime(firstTime);
            setPlaying((value) => !value);
          }}
          disabled={orderedPoints.length < 2}
          aria-label={playing ? 'Pause location playback' : 'Play location playback'}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <button type="button" onClick={() => seek(60000)} disabled={currentTime >= lastTime}>Forward 1 minute</button>
        <label>
          Playback speed{' '}
          <select
            value={speed}
            onChange={(event) => setSpeed(Number(event.target.value))}
          >
            <option value={1}>1×</option>
            <option value={2}>2×</option>
            <option value={5}>5×</option>
            <option value={10}>10×</option>
          </select>
        </label>
      </div>
      <label htmlFor={`location-scrubber-${agentId}`}>
        Playback time
      </label>
      <input
        id={`location-scrubber-${agentId}`}
        type="range"
        min={firstTime}
        max={lastTime}
        step={1000}
        value={currentTime}
        onChange={(event) => {
          setPlaying(false);
          setCurrentTime(Number(event.target.value));
        }}
        style={{ display: 'block', width: '100%' }}
        aria-valuetext={new Date(currentTime).toLocaleString()}
      />
      <p style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <span>Route start: {new Date(firstTime).toLocaleString()}{orderedPoints[0].is_simulated ? ' · Demo data' : ''}</span>
        <span>Route end: {new Date(lastTime).toLocaleString()}{orderedPoints[orderedPoints.length - 1].is_simulated ? ' · Demo data' : ''}</span>
      </p>
    </div>
  );
};

const AllAgentLocationPlayback = ({ agents, start, end }) => {
  const startTime = new Date(start).getTime();
  const endTime = new Date(end).getTime();
  const routes = useMemo(
    () => agents.map((agent) => ({
      ...agent,
      points: [...agent.points].sort(
        (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime(),
      ),
    })),
    [agents],
  );
  const routePositions = useMemo(
    () => routes.flatMap((agent) => agent.points.map(
      (point) => [point.latitude, point.longitude],
    )),
    [routes],
  );
  const [currentTime, setCurrentTime] = useState(startTime);
  const [playingDirection, setPlayingDirection] = useState(0);
  const [speed, setSpeed] = useState(60);

  useEffect(() => {
    setCurrentTime(startTime);
    setPlayingDirection(0);
  }, [startTime, endTime, agents]);

  useEffect(() => {
    if (!playingDirection) return undefined;
    if (
      (playingDirection > 0 && currentTime >= endTime)
      || (playingDirection < 0 && currentTime <= startTime)
    ) {
      setPlayingDirection(0);
      return undefined;
    }
    const timer = window.setInterval(() => {
      setCurrentTime((time) => Math.max(
        startTime,
        Math.min(endTime, time + playingDirection * 250 * speed),
      ));
    }, 250);
    return () => window.clearInterval(timer);
  }, [currentTime, endTime, playingDirection, speed, startTime]);

  if (routePositions.length === 0) {
    return <p>No location history is available for the selected period.</p>;
  }

  const visibleAgents = routes.flatMap((agent, index) => {
    const firstPoint = agent.points[0];
    if (!firstPoint || currentTime < new Date(firstPoint.recorded_at).getTime()) return [];

    let previousPoint = firstPoint;
    let nextPoint = null;
    for (let pointIndex = 1; pointIndex < agent.points.length; pointIndex += 1) {
      const pointTime = new Date(agent.points[pointIndex].recorded_at).getTime();
      if (pointTime >= currentTime) {
        previousPoint = agent.points[pointIndex - 1];
        nextPoint = agent.points[pointIndex];
        break;
      }
      previousPoint = agent.points[pointIndex];
    }

    const previousTime = new Date(previousPoint.recorded_at).getTime();
    const nextTime = nextPoint ? new Date(nextPoint.recorded_at).getTime() : previousTime;
    const interpolation = !nextPoint || nextTime === previousTime
      ? 0
      : Math.max(0, Math.min(1, (currentTime - previousTime) / (nextTime - previousTime)));
    const position = {
      latitude: previousPoint.latitude
        + ((nextPoint?.latitude ?? previousPoint.latitude) - previousPoint.latitude) * interpolation,
      longitude: previousPoint.longitude
        + ((nextPoint?.longitude ?? previousPoint.longitude) - previousPoint.longitude) * interpolation,
      is_simulated: previousPoint.is_simulated || Boolean(nextPoint?.is_simulated),
    };
    const completedRoute = agent.points
      .filter((point) => new Date(point.recorded_at).getTime() <= currentTime)
      .map((point) => [point.latitude, point.longitude]);
    completedRoute.push([position.latitude, position.longitude]);

    return [{ ...agent, index, position, completedRoute }];
  });
  const mapCenter = visibleAgents.length
    ? [visibleAgents[0].position.latitude, visibleAgents[0].position.longitude]
    : [-1.2864, 36.8172];
  const visibleByUserId = new Map(
    visibleAgents.map((agent) => [agent.user_id, agent]),
  );
  const movePlayback = (direction) => {
    if (playingDirection === direction) {
      setPlayingDirection(0);
      return;
    }
    if (direction > 0 && currentTime >= endTime) setCurrentTime(startTime);
    if (direction < 0 && currentTime <= startTime) setCurrentTime(endTime);
    setPlayingDirection(direction);
  };

  return (
    <div>
      <LocationMap
        points={routePositions}
        center={mapCenter}
        zoom={6}
        label="Map of all agent locations at the selected playback time"
      >
        {routes.map((agent, index) => {
          const color = ['#874b17', '#783a12', '#d97620', '#934908', '#b46118'][index % 5];
          const visibleAgent = visibleByUserId.get(agent.user_id);
          return (
            <React.Fragment key={agent.user_id}>
              {agent.points.length > 1 && (
                <Polyline
                  positions={agent.points.map((point) => [point.latitude, point.longitude])}
                  pathOptions={{ color, weight: 3, opacity: 0.25 }}
                />
              )}
              {visibleAgent && (
                <>
                  {visibleAgent.completedRoute.length > 1 && (
                    <Polyline
                      positions={visibleAgent.completedRoute}
                      pathOptions={{ color, weight: 5, opacity: 0.9 }}
                    />
                  )}
                  <CircleMarker
                    center={[visibleAgent.position.latitude, visibleAgent.position.longitude]}
                    radius={9}
                    pathOptions={{ color, fillColor: color, fillOpacity: 1 }}
                  >
                    <Popup>
                      <strong>{agent.name}</strong>
                      <br />
                      {agent.department || 'Unassigned'}
                      <br />
                      {new Date(currentTime).toLocaleString()}
                      {visibleAgent.position.is_simulated && (
                        <>
                          <br />
                          Demo data — not live GPS
                        </>
                      )}
                    </Popup>
                  </CircleMarker>
                </>
              )}
            </React.Fragment>
          );
        })}
      </LocationMap>
      <p aria-live="polite">
        {new Date(currentTime).toLocaleString()}
        {' · '}{visibleAgents.length} of {routes.length} agents have a location at this time
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <button
          type="button"
          onClick={() => movePlayback(-1)}
          disabled={startTime >= endTime}
          aria-pressed={playingDirection === -1}
        >
          Play reverse
        </button>
        <button
          type="button"
          onClick={() => setPlayingDirection(0)}
          disabled={!playingDirection}
        >
          Pause
        </button>
        <button
          type="button"
          onClick={() => movePlayback(1)}
          disabled={startTime >= endTime}
          aria-pressed={playingDirection === 1}
        >
          Play forward
        </button>
        <label>
          Playback speed{' '}
          <select
            value={speed}
            onChange={(event) => setSpeed(Number(event.target.value))}
          >
            <option value={1}>1×</option>
            <option value={10}>10×</option>
            <option value={60}>60×</option>
            <option value={300}>300×</option>
          </select>
        </label>
      </div>
      <label htmlFor="all-agent-location-scrubber">Playback time</label>
      <input
        id="all-agent-location-scrubber"
        type="range"
        min={startTime}
        max={endTime}
        step={1000}
        value={currentTime}
        onChange={(event) => {
          setPlayingDirection(0);
          setCurrentTime(Number(event.target.value));
        }}
        style={{ display: 'block', width: '100%' }}
        aria-valuetext={new Date(currentTime).toLocaleString()}
      />
      <p style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <span>Period start: {new Date(startTime).toLocaleString()}</span>
        <span>Period end: {new Date(endTime).toLocaleString()}</span>
      </p>
    </div>
  );
};

export const LiveLocationDashboard = () => {
  const [agents, setAgents] = useState([]);
  const [trailByAgent, setTrailByAgent] = useState({});
  const [allAgentHistory, setAllAgentHistory] = useState(null);
  const [allAgentHistoryLoading, setAllAgentHistoryLoading] = useState(false);
  const [allAgentHistoryError, setAllAgentHistoryError] = useState('');
  const [error, setError] = useState('');
  const [controlError, setControlError] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');
  const [trackingControl, setTrackingControl] = useState(null);
  const [controlBusy, setControlBusy] = useState(false);
  const lastStreamUpdateAt = useRef(0);
  const [historyRange, setHistoryRange] = useState(() => {
    const end = new Date();
    return {
      start: asLocalDateTimeInput(new Date(end.getTime() - 24 * 60 * 60 * 1000)),
      end: asLocalDateTimeInput(end),
    };
  });
  const liveMapPoints = useMemo(
    () => agents
      .filter((agent) => Number.isFinite(agent.latitude) && Number.isFinite(agent.longitude))
      .map((agent) => [agent.latitude, agent.longitude]),
    [agents],
  );

  const receiveLiveLocations = useCallback((data, isStreamUpdate = false) => {
    if (isStreamUpdate) lastStreamUpdateAt.current = Date.now();
    setAgents(data.agents || []);
    setUpdatedAt(data.refreshed_at || '');
    setError('');
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await organizationApi.getLiveLocations();
      receiveLiveLocations(data);
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    }
  }, [receiveLiveLocations]);

  const refreshTrackingControl = useCallback(async () => {
    try {
      const data = await organizationApi.getLocationTrackingControl();
      setTrackingControl(data);
      setControlError('');
    } catch (requestError) {
      if (requestError.status === 403) {
        setTrackingControl(null);
        setControlError('');
      } else {
        setControlError(requestError.message);
      }
    }
  }, []);

  const toggleTrackingControl = async () => {
    if (!trackingControl) return;
    setControlBusy(true);
    setControlError('');
    try {
      const data = await organizationApi.setLocationTrackingControl(!trackingControl.enabled);
      setTrackingControl(data);
    } catch (requestError) {
      setControlError(requestError.message);
    } finally {
      setControlBusy(false);
    }
  };

  const loadTrail = async (agentId, range = historyRange) => {
    const start = new Date(range.start);
    const end = new Date(range.end);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start >= end) {
      setTrailByAgent((current) => ({
        ...current,
        [agentId]: {
          ...current[agentId],
          open: true,
          loading: false,
          error: 'Choose a valid start and end time; the start must be earlier than the end.',
        },
      }));
      return;
    }
    setTrailByAgent((current) => ({
      ...current,
      [agentId]: {
        ...current[agentId],
        open: true,
        start: range.start,
        end: range.end,
        loading: true,
        error: '',
      },
    }));
    try {
      const result = await organizationApi.getAgentLocationTrail(agentId, start, end);
      setTrailByAgent((current) => ({
        ...current,
        [agentId]: {
          open: true,
          start: range.start,
          end: range.end,
          loading: false,
          error: '',
          points: result.trail || [],
        },
      }));
    } catch (requestError) {
      setTrailByAgent((current) => ({
        ...current,
        [agentId]: {
          ...current[agentId],
          open: true,
          loading: false,
          error: requestError.message,
        },
      }));
    }
  };

  const loadAllAgentHistory = async () => {
    const start = new Date(historyRange.start);
    const end = new Date(historyRange.end);
    if (
      Number.isNaN(start.getTime())
      || Number.isNaN(end.getTime())
      || start >= end
      || end > new Date()
    ) {
      setAllAgentHistoryError('Choose a valid period in the past; the start must be earlier than the end.');
      return;
    }
    if (agents.length === 0) {
      setAllAgentHistory([]);
      setAllAgentHistoryError('');
      return;
    }

    setAllAgentHistory(null);
    setAllAgentHistoryLoading(true);
    setAllAgentHistoryError('');
    try {
      const results = [];
      for (let offset = 0; offset < agents.length; offset += 10) {
        const batch = await Promise.all(agents.slice(offset, offset + 10).map(async (agent) => {
          const result = await organizationApi.getAgentLocationTrail(agent.user_id, start, end);
          return {
            user_id: agent.user_id,
            name: agent.name,
            department: agent.department,
            points: result.trail || [],
          };
        }));
        results.push(...batch);
      }
      setAllAgentHistory(results);
    } catch (requestError) {
      setAllAgentHistoryError(requestError.message);
    } finally {
      setAllAgentHistoryLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    let retryTimer;
    const controller = new AbortController();
    lastStreamUpdateAt.current = Date.now();
    refresh();
    const fallbackTimer = window.setInterval(() => {
      if (Date.now() - lastStreamUpdateAt.current >= 30000) refresh();
    }, 15000);
    const waitBeforeRetry = () => new Promise((resolve) => {
      const finish = () => {
        window.clearTimeout(retryTimer);
        controller.signal.removeEventListener('abort', finish);
        resolve();
      };
      retryTimer = window.setTimeout(finish, 15000);
      controller.signal.addEventListener('abort', finish, { once: true });
    });
    const connect = async () => {
      while (active) {
        let streamError = '';
        try {
          await organizationApi.streamLiveLocations(
            (data) => receiveLiveLocations(data, true),
            controller.signal,
          );
          streamError = 'The live location stream closed.';
        } catch (requestError) {
          if (!active || controller.signal.aborted) return;
          streamError = requestError.message;
        }
        if (!active) return;
        const refreshed = await refresh();
        if (!active) return;
        if (refreshed) {
          setError(`Live push paused (${streamError}); reconnecting with 15-second refreshes.`);
        }
        await waitBeforeRetry();
      }
    };
    connect();
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(retryTimer);
      window.clearInterval(fallbackTimer);
    };
  }, [receiveLiveLocations, refresh]);

  useEffect(() => {
    refreshTrackingControl();
    const timer = window.setInterval(refreshTrackingControl, 30000);
    return () => window.clearInterval(timer);
  }, [refreshTrackingControl]);

  return (
    <main style={pageStyle}>
      <header>
        <h1>Agent live locations</h1>
        <p>Scheduled tracking runs automatically for active field agents. Their browser must be signed in, visible, and permitted to access GPS.</p>
        <p>Live positions arrive over an authenticated event stream. If it disconnects, the dashboard falls back to a 15-second refresh.</p>
        {updatedAt && <small>Updated {new Date(updatedAt).toLocaleTimeString()}</small>}
      </header>
      {error && <p style={errorText} role="alert">{error}</p>}
      <section aria-label="All-agent location playback" style={cardStyle}>
        <h2>All-agent location playback</h2>
        <p>
          Load recorded locations for all agents in your management scope. Choose a time to see their
          positions together; use forward or reverse playback to follow their recorded movement.
          Positions between GPS updates are interpolated. The live map below continues updating in real time.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: 12, margin: '12px 0' }}>
          <label>
            From{' '}
            <input
              type="datetime-local"
              value={historyRange.start}
              onChange={(event) => {
                setHistoryRange((range) => ({ ...range, start: event.target.value }));
                setAllAgentHistory(null);
                setAllAgentHistoryError('');
              }}
              disabled={allAgentHistoryLoading}
            />
          </label>
          <label>
            To{' '}
            <input
              type="datetime-local"
              value={historyRange.end}
              onChange={(event) => {
                setHistoryRange((range) => ({ ...range, end: event.target.value }));
                setAllAgentHistory(null);
                setAllAgentHistoryError('');
              }}
              disabled={allAgentHistoryLoading}
            />
          </label>
          <button
            type="button"
            onClick={loadAllAgentHistory}
            disabled={allAgentHistoryLoading}
          >
            {allAgentHistoryLoading ? 'Loading agent locations…' : 'Load all agent locations'}
          </button>
          <small>Location history is retained for up to 30 days.</small>
        </div>
        {allAgentHistoryError && <p style={errorText} role="alert">{allAgentHistoryError}</p>}
        {allAgentHistoryLoading && <p role="status">Loading location history for all agents…</p>}
        {!allAgentHistoryLoading && allAgentHistory && (
          <AllAgentLocationPlayback
            agents={allAgentHistory}
            start={historyRange.start}
            end={historyRange.end}
          />
        )}
      </section>
      {trackingControl && (
        <section style={cardStyle} aria-label="Agent tracking controls">
          <h2>{trackingControl.scope.label} tracking</h2>
          <p>
            {trackingControl.schedule_configured
              ? trackingControl.scheduled_enabled
              ? `System schedule is active (${trackingControl.timezone || 'Africa/Nairobi'}).`
                : 'System schedule is currently off. Managers can change tracking during scheduled hours.'
              : 'Tracking is off until a system administrator configures a schedule.'}
            {trackingControl.override_active && trackingControl.override_expires_at
              ? ` Your temporary override ends ${new Date(trackingControl.override_expires_at).toLocaleString()}.`
              : ''}
          </p>
          <button
            className="leave-secondary-button"
            type="button"
            onClick={toggleTrackingControl}
            disabled={
              controlBusy
              || !trackingControl.schedule_configured
              || !trackingControl.scheduled_enabled
            }
            aria-pressed={trackingControl.enabled}
          >
            {controlBusy
              ? 'Updating…'
              : trackingControl.enabled
                ? 'Pause agent tracking'
                : 'Resume agent tracking'}
          </button>
          {!trackingControl.scheduled_enabled && trackingControl.schedule_configured && (
            <p>Tracking follows the administrator schedule outside its active hours.</p>
          )}
          {controlError && <p style={errorText} role="alert">{controlError}</p>}
        </section>
      )}
      {controlError && !trackingControl && <p style={errorText} role="alert">{controlError}</p>}
      {agents.length === 0 && !error && <p>No location updates have been received in the last 24 hours.</p>}
      {agents.length > 0 && liveMapPoints.length === 0 && !error && <p>No location updates have been received in the last 24 hours.</p>}
      {liveMapPoints.length > 0 && (
        <section aria-label="Live agent map" style={cardStyle}>
          <h2>Live agent map</h2>
          <p>Markers show the latest GPS updates. Simulated demo locations are marked and are not live GPS.</p>
          <LocationMap
            points={liveMapPoints}
            center={[0.0236, 37.9062]}
            zoom={6}
            fitPoints={false}
            label="Live map of tracked field agents"
          >
            {agents.filter((agent) => Number.isFinite(agent.latitude) && Number.isFinite(agent.longitude)).map((agent, index) => {
              const trail = (agent.trail || []).map((point) => [point.latitude, point.longitude]);
              const color = ['#874b17', '#783a12', '#f7a863', '#d97620', '#934908'][index % 5];
              return (
                <React.Fragment key={agent.user_id}>
                  {trail.length > 1 && (
                    <Polyline
                      positions={trail}
                      pathOptions={{
                        color: agent.is_simulated ? '#bd5e0a' : color,
                        weight: 4,
                        opacity: 0.75,
                        dashArray: agent.is_simulated ? '8 8' : undefined,
                      }}
                    />
                  )}
                  <CircleMarker
                    center={[agent.latitude, agent.longitude]}
                    radius={9}
                    pathOptions={{
                      color: agent.is_simulated ? '#783a12' : '#783a12',
                      fillColor: agent.is_simulated ? '#f2780e' : '#e9740e',
                      fillOpacity: 1,
                    }}
                  >
                    <Popup>
                      <strong>{agent.name}</strong>
                      <br />
                      {agent.department || 'Unassigned'}
                      <br />
                      {agent.active_visit ? 'Active field visit · opt-in sharing' : 'Scheduled tracking'}
                      <br />
                      {agent.is_simulated ? 'Demo data — not live GPS' : agent.is_live ? 'Live' : 'Last known'}
                      <br />
                      {new Date(agent.recorded_at).toLocaleString()}
                    </Popup>
                  </CircleMarker>
                </React.Fragment>
              );
            })}
          </LocationMap>
        </section>
      )}
      {agents.map((agent) => (
        <article style={cardStyle} key={agent.user_id}>
          <h2>{agent.name} <small>
            {agent.active_visit
              ? agent.sharing_status === 'on' ? 'Active field visit · sharing now' : 'Active field visit · awaiting location'
              : agent.sharing_status === 'on'
              ? 'Tracking now'
              : agent.sharing_status === 'stale'
                ? 'Scheduled · no recent update'
                : agent.override_active && agent.scheduled_enabled
                  ? 'Paused by manager'
                  : 'Outside schedule'}
          </small></h2>
          <p>{agent.department || 'Unassigned'}{agent.recorded_at ? ` · ${new Date(agent.recorded_at).toLocaleString()}` : ''}</p>
          {Number.isFinite(agent.latitude) && Number.isFinite(agent.longitude) ? (
            <>
              <p>{agent.latitude.toFixed(5)}, {agent.longitude.toFixed(5)}{agent.accuracy_meters ? ` · ±${Math.round(agent.accuracy_meters)} m` : ''}</p>
              <a
                href={`https://maps.google.com/?q=${agent.latitude},${agent.longitude}`}
                target="_blank"
                rel="noreferrer"
              >
                Open latest position in Maps
              </a>
            </>
          ) : <p>No location received in the last 24 hours.</p>}
          <button
            type="button"
            onClick={() => {
              if (trailByAgent[agent.user_id]?.open) {
                setTrailByAgent((current) => ({
                  ...current,
                  [agent.user_id]: { ...current[agent.user_id], open: false },
                }));
              } else {
                loadTrail(agent.user_id);
              }
            }}
          >
            {trailByAgent[agent.user_id]?.open ? 'Hide movement trail' : 'View movement history'}
          </button>
          {trailByAgent[agent.user_id]?.open && (
            <section aria-label={`${agent.name} movement trail`}>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: 12, margin: '12px 0' }}>
                <label>
                  From{' '}
                  <input
                    type="datetime-local"
                    value={historyRange.start}
                    onChange={(event) => setHistoryRange((range) => ({ ...range, start: event.target.value }))}
                    disabled={trailByAgent[agent.user_id].loading}
                  />
                </label>
                <label>
                  To{' '}
                  <input
                    type="datetime-local"
                    value={historyRange.end}
                    onChange={(event) => setHistoryRange((range) => ({ ...range, end: event.target.value }))}
                    disabled={trailByAgent[agent.user_id].loading}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => loadTrail(agent.user_id)}
                  disabled={trailByAgent[agent.user_id].loading}
                >
                  Load selected period
                </button>
                <small>History is retained for up to 30 days.</small>
              </div>
              {trailByAgent[agent.user_id].loading && <p role="status">Loading movement history…</p>}
              {trailByAgent[agent.user_id].error && <p style={errorText} role="alert">{trailByAgent[agent.user_id].error}</p>}
              {!trailByAgent[agent.user_id].loading && !trailByAgent[agent.user_id].error && (
                <LocationTrailPlayback
                  points={trailByAgent[agent.user_id].points}
                  name={agent.name}
                  agentId={agent.user_id}
                />
              )}
            </section>
          )}
          {agent.trail.length > 1 && (() => {
            const latitudes = agent.trail.map((point) => point.latitude);
            const longitudes = agent.trail.map((point) => point.longitude);
            const minLatitude = Math.min(...latitudes);
            const maxLatitude = Math.max(...latitudes);
            const minLongitude = Math.min(...longitudes);
            const maxLongitude = Math.max(...longitudes);
            const latitudeSpan = maxLatitude - minLatitude || 0.00001;
            const longitudeSpan = maxLongitude - minLongitude || 0.00001;
            const points = agent.trail.map((point) => ({
              x: 20 + ((point.longitude - minLongitude) / longitudeSpan) * 460,
              y: 160 - ((point.latitude - minLatitude) / latitudeSpan) * 140,
            }));
            return (
              <>
                <svg viewBox="0 0 500 180" role="img" aria-label={`${agent.name} travel trail`} style={{ width: '100%', maxHeight: 220, marginTop: 12, background: '#faf7f5', borderRadius: 8 }}>
                  <polyline points={points.map((point) => `${point.x},${point.y}`).join(' ')} fill="none" stroke="#874b17" strokeWidth="3" />
                  {points.map((point, index) => (
                    <circle
                      key={`${agent.trail[index].recorded_at}-${index}`}
                      cx={point.x}
                      cy={point.y}
                      r="4"
                      fill={agent.trail[index].is_simulated ? '#bd5e0a' : '#874b17'}
                    />
                  ))}
                </svg>
                {agent.trail.some((point) => point.is_simulated) && (
                  <p><strong>Demo data points are not live GPS.</strong></p>
                )}
              </>
            );
          })()}
          <details>
            <summary>Travel trail ({agent.trail.length} points)</summary>
            <ol>
              {agent.trail.map((point, index) => (
                <li key={`${point.recorded_at}-${index}`}>
                  {new Date(point.recorded_at).toLocaleString()} — {point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}
                  {point.is_simulated ? ' · Demo data — not live GPS' : ''}
                </li>
              ))}
            </ol>
          </details>
        </article>
      ))}
    </main>
  );
};
