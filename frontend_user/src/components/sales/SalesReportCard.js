import React from 'react';

export const SalesReportCard = ({ title = "Today's report", value = 'Not filed', onAction }) => {
	const actionLabel = value === 'Not filed' ? 'File now' : 'View report';

	return <article className="sales-v2-card sales-v2-report-card">
		<span>{title}</span>
		<strong>{value}</strong>
		<button type="button" onClick={() => onAction?.()} aria-label={`${actionLabel}: ${title}`}>
			{actionLabel}
		</button>
	</article>;
};
