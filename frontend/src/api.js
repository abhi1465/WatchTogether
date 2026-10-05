const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).trim().replace(/\/+$/, "");

export async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      signal: controller.signal,
    });

    const data = await response.json();

    if (!response.ok) {
      const message =
        typeof data.detail === "string"
          ? data.detail
          : "Please check your selections and try again.";

      throw new Error(message);
    }

    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The request took too long. Please try again.");
    }

    if (error instanceof TypeError) {
      throw new Error(
        "Cannot reach the recommendation service. Please try again shortly."
      );
    }

    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
