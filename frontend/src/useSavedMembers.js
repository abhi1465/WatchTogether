import { useEffect, useState } from "react";

const STORAGE_KEY = "watchtogether.members.v1";

function defaultMembers() {
  return [
    { id: "you", name: "You", favourites: [] },
    { id: "friend", name: "Friend", favourites: [] },
  ];
}

function validMembers(value) {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    value.length <= 10 &&
    value[0]?.id === "you" &&
    new Set(value.map((member) => member?.id)).size === value.length &&
    value.every(
      (member) =>
        member &&
        typeof member.id === "string" &&
        typeof member.name === "string" &&
        member.name.length <= 40 &&
        Array.isArray(member.favourites) &&
        member.favourites.length <= 20 &&
        member.favourites.every(
          (movie) =>
            movie &&
            Number.isInteger(movie.movieId) &&
            movie.movieId > 0 &&
            typeof movie.title === "string"
        )
    )
  );
}

function loadMembers() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return validMembers(saved) ? saved : defaultMembers();
  } catch {
    return defaultMembers();
  }
}

export function useSavedMembers() {
  const [members, setMembers] = useState(loadMembers);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(members));
      setSaveError("");
    } catch {
      setSaveError(
        "Browser storage is unavailable. Your selections work for this session, but may not survive a refresh."
      );
    }
  }, [members]);

  return [members, setMembers, saveError];
}