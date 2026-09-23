const API_ORIGIN = process.env.REACT_APP_API_URL || '';

export const apiUrl = (path) => `${API_ORIGIN}${path}`;
