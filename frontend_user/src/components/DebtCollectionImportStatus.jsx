import React from 'react';

export default function DebtCollectionImportStatus({
  fileName,
  status,
  progress,
  message,
  issues = [],
}) {
  if (!fileName && !message) return null;

  const active = status === 'uploading' || status === 'processing';
  const failed = status === 'failed';
  const tone = failed ? 'error' : status === 'success' ? 'success' : status === 'partial' ? 'warning' : 'info';

  return (
    <section className={`debt-import-status ${tone}`} aria-label="Import status" aria-live={failed ? 'assertive' : 'polite'}>
      {fileName && <p><strong>Selected file:</strong> {fileName}</p>}
      {active && (
        <div className="debt-import-progress">
          <div className="debt-import-progress-label">
            <span>{status === 'uploading' ? 'Uploading file…' : 'File uploaded; processing rows…'}</span>
            {status === 'uploading' && <span>{progress}%</span>}
          </div>
          <progress aria-label="Import progress" max="100" value={status === 'uploading' ? progress : undefined} />
        </div>
      )}
      {message && <p role={failed ? 'alert' : 'status'}><strong>{message}</strong></p>}
      {issues.length > 0 && (
        <div>
          <strong>Rows needing correction</strong>
          <ul>{issues.slice(0, 10).map((issue) => <li key={`${issue.row_number}-${issue.message}`}>Row {issue.row_number}: {issue.message}</li>)}</ul>
          {issues.length > 10 && <p>{issues.length - 10} more row errors were returned by the import.</p>}
        </div>
      )}
    </section>
  );
}
