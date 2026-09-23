/**
 * Application Entry Point
 * Renders the React application into the DOM
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import './styles/colors.css';
import './styles/typography.css';
import './styles/spacing.css';
import './styles/Accessibility.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);