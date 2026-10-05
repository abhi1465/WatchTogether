import { apiRequest } from "./api";

const MAX_CONCURRENT = 3;

const cache = new Map();
const pendingRequests = new Map();
const queue = [];

let activeRequests = 0;

function runQueue() {
  while (activeRequests < MAX_CONCURRENT && queue.length > 0) {
    const task = queue.shift();
    activeRequests += 1;

    Promise.resolve()
      .then(task.run)
      .then(task.resolve, task.reject)
      .finally(() => {
        activeRequests -= 1;
        runQueue();
      });
  }
}

function enqueue(run) {
  return new Promise((resolve, reject) => {
    queue.push({ run, resolve, reject });
    runQueue();
  });
}

export function getCachedMetadata(movieId) {
  return cache.get(movieId) || null;
}

export function fetchMovieMetadata(movieId) {
  if (cache.has(movieId)) {
    return Promise.resolve(cache.get(movieId));
  }

  if (pendingRequests.has(movieId)) {
    return pendingRequests.get(movieId);
  }

  const request = enqueue(() =>
    apiRequest(`/api/movies/${movieId}/metadata`)
  )
    .then((data) => {
      cache.set(movieId, data);
      return data;
    })
    .finally(() => {
      pendingRequests.delete(movieId);
    });

  pendingRequests.set(movieId, request);
  return request;
}