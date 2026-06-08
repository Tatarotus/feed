const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  const response = await fetch(url, {
    ...options,
    headers
  });

  if (response.status === 204) {
    return null;
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export const api = {
  // Feed Recommendations
  getFeed: (limit = 30, serendipity = 0.2) => request(`/feed?limit=${limit}&serendipity=${serendipity}`),
  getShortsFeed: (limit = 30, serendipity = 0.2) => request(`/feed/shorts?limit=${limit}&serendipity=${serendipity}`),

  // Channel Subscriptions
  getChannels: () => request("/channels"),
  createChannel: (channelData) => request("/channels", {
    method: "POST",
    body: JSON.stringify(channelData)
  }),
  updateChannel: (channelId, updateData) => request(`/channels/${channelId}`, {
    method: "PATCH",
    body: JSON.stringify(updateData)
  }),
  deleteChannel: (channelId) => request(`/channels/${channelId}`, {
    method: "DELETE"
  }),
  syncChannel: (channelId) => request(`/channels/${channelId}/sync`, {
    method: "POST"
  }),

  // Queue ("Read Later")
  getQueue: () => request("/queue"),
  addToQueue: (videoId, priority = 0) => request("/queue", {
    method: "POST",
    body: JSON.stringify({ video_id: videoId, priority })
  }),
  consumeQueueItem: (videoId) => request(`/queue/${videoId}/consume`, {
    method: "POST"
  }),
  dequeueVideo: (videoId) => request(`/queue/${videoId}`, {
    method: "DELETE"
  }),

  // Topic Interests
  getInterests: () => request("/interests"),
  followTopic: (topic, weight = 1.0) => request("/interests", {
    method: "POST",
    body: JSON.stringify({ topic, weight })
  }),
  unfollowTopic: (interestId) => request(`/interests/${interestId}`, {
    method: "DELETE"
  }),
  updateInterestWeight: (interestId, updateData) => request(`/interests/${interestId}`, {
    method: "PATCH",
    body: JSON.stringify(updateData)
  }),
  addManualSeed: (seedData) => request("/interests/seed", {
    method: "POST",
    body: JSON.stringify(seedData)
  }),
  getMutations: () => request("/interests/mutations"),

  // Diagnostics & Logs
  explainScoring: (videoId) => request(`/debug/explain/${videoId}`),
  triggerPipelineSync: () => request("/debug/pipeline/run", { method: "POST" }),
  logEvent: (videoId, eventType, watchTimePct = 0.0, rating = null) => {
    // Fire-and-forget telemetry events
    const query = new URLSearchParams({
      video_id: videoId,
      event_type: eventType,
      watch_time_pct: watchTimePct.toString()
    });
    if (rating !== null) {
      query.append("rating", rating.toString());
    }
    return request(`/debug/events?${query.toString()}`, { method: "POST" }).catch(err => {
      console.error("Telemetry event failed:", err);
    });
  },

  likeVideo: (videoId) => api.logEvent(videoId, "like", 0.0, 1),
  dislikeVideo: (videoId) => api.logEvent(videoId, "dislike", 0.0, -1),

  getLikedVideos: (sortBy = "newest", search = "", limit = 50, offset = 0) => {
    const params = new URLSearchParams({ sort_by: sortBy, limit: limit.toString(), offset: offset.toString() });
    if (search) {
      params.append("search", search);
    }
    return request(`/feed/liked?${params.toString()}`);
  },

  // Search
  search: (query, limit = 25) => request(`/search?q=${encodeURIComponent(query)}&limit=${limit}`)
};
