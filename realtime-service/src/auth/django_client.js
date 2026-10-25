/**
 * Django authorization client for the realtime service.
 *
 * All authorization decisions are delegated to Django as the authoritative source
 * for user identity, roles, and consultation membership. Knowing a room ID is
 * never sufficient to gain access.
 */

const DJANGO_API_URL = process.env.DJANGO_API_URL || 'http://localhost:8000';
/**
 * Verifies that the authenticated user is a participant in the consultation
 * identified by roomId, and that the consultation is in an accessible state.
 *
 * Returns the consultation object on success, or null on failure.
 *
 * @param {string} userToken - The user's JWT access token for impersonation.
 * @param {string} roomId - The consultation room_id UUID.
 * @returns {Promise<{consultationId: string, roomId: string, status: string, userId: string} | null>}
 */
export async function verifyConsultationMembership(userToken, roomId) {
  if (!roomId || !userToken) return null;

  try {
    const url = `${DJANGO_API_URL}/api/consultations/?room_id=${encodeURIComponent(roomId)}`;
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${userToken}`,
        Accept: 'application/json',
      },
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) return null;

    const data = await res.json();
    const results = Array.isArray(data) ? data : (data.results || []);
    const consultation = results.find((c) => String(c.room_id) === String(roomId));
    if (!consultation) return null;

    return {
      consultationId: String(consultation.id),
      roomId: String(consultation.room_id),
      status: consultation.status,
    };
  } catch {
    // Fail closed: if Django is unreachable, deny access
    return null;
  }
}

/**
 * Persists a chat message to Django via REST API.
 * Uses the user's own token to enforce server-side sender attribution.
 *
 * Returns the persisted message (with server-assigned ID and timestamp),
 * or null on failure.
 */
export async function persistMessage({ consultationId, userToken, message, clientMsgId }) {
  if (!consultationId || !userToken || !message) return null;

  try {
    const url = `${DJANGO_API_URL}/api/consultations/${encodeURIComponent(consultationId)}/messages/`;
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${userToken}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        message,
        client_msg_id: clientMsgId || '',
      }),
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Fetches paginated message history from Django.
 * Returns {results, count, next, previous} or null on failure.
 */
export async function fetchMessageHistory({ consultationId, userToken, page = 1, pageSize = 50 }) {
  if (!consultationId || !userToken) return null;

  try {
    const url = `${DJANGO_API_URL}/api/consultations/${encodeURIComponent(consultationId)}/messages/?page=${page}&page_size=${pageSize}`;
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${userToken}`,
        Accept: 'application/json',
      },
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchIdentity(token) {
  try {
    const res = await fetch(`${DJANGO_API_URL}/api/consultations/identity/`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const user = await res.json();
    return user.id && ['patient', 'doctor', 'admin'].includes(user.role) ? user : null;
  } catch { return null; }
}
