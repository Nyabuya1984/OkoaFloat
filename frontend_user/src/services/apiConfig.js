const API_ORIGIN = process.env.REACT_APP_API_URL || '';

export const apiUrl = (path) => `${API_ORIGIN}${path}`;

export const readJsonResponse = async (response, fallbackMessage = 'The server responded unexpectedly.') => {
  const rawText = await response.text();
  if (!rawText) return {};

  try {
    return JSON.parse(rawText);
  } catch (error) {
    return { error: { message: fallbackMessage }, message: fallbackMessage };
  }
};
