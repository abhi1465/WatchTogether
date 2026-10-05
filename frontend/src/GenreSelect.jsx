import { useEffect, useId, useRef, useState } from "react";

export default function GenreSelect({
  value,
  genres,
  onChange,
  disabled = false,
  loading = false,
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const listRef = useRef(null);
  const id = useId();

  const options = [
    { value: "", label: "Any genre" },
    ...genres.map((genre) => ({ value: genre, label: genre })),
  ];

  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value)
  );

  useEffect(() => {
    if (!open) return;

    listRef.current?.focus();

    function closeOnOutsideClick(event) {
      if (!rootRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);

    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      listRef.current
        ?.querySelector(`[data-index="${activeIndex}"]`)
        ?.scrollIntoView({ block: "nearest" });
    }
  }, [open, activeIndex]);

  function openMenu() {
    if (disabled) return;
    setActiveIndex(selectedIndex);
    setOpen(true);
  }

  function selectOption(index) {
    if (disabled) return;

    onChange(options[index].value);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function handleKeys(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex(
        (current) => (current - 1 + options.length) % options.length
      );
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(options.length - 1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectOption(activeIndex);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    } else if (
      event.key.length === 1 &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey
    ) {
      const letter = event.key.toLowerCase();

      for (let offset = 1; offset <= options.length; offset += 1) {
        const index = (activeIndex + offset) % options.length;

        if (options[index].label.toLowerCase().startsWith(letter)) {
          event.preventDefault();
          setActiveIndex(index);
          break;
        }
      }
    }
  }

  return (
    <div
      className="genre-picker"
      ref={rootRef}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setOpen(false);
        }
      }}
    >
      <span className="genre-label" id={`${id}-label`}>
        What kind of film tonight?
      </span>

      <button
        ref={triggerRef}
        type="button"
        className="genre-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined}
        aria-labelledby={`${id}-label ${id}-value`}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            openMenu();
          }
        }}
      >
        <span id={`${id}-value`}>
          {loading ? "Loading genres…" : value || "Any genre"}
        </span>
        <span className="genre-chevron" aria-hidden="true">
          {open ? "▴" : "▾"}
        </span>
      </button>

      {open && (
        <div
          ref={listRef}
          id={`${id}-list`}
          className="genre-options"
          role="listbox"
          tabIndex={0}
          aria-labelledby={`${id}-label`}
          aria-activedescendant={`${id}-option-${activeIndex}`}
          onKeyDown={handleKeys}
        >
          {options.map((option, index) => (
            <div
              key={option.value}
              id={`${id}-option-${index}`}
              data-index={index}
              role="option"
              aria-selected={value === option.value}
              className={`genre-option ${
                activeIndex === index ? "is-active" : ""
              } ${value === option.value ? "is-selected" : ""}`}
              onPointerMove={() => setActiveIndex(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectOption(index)}
            >
              <span>{option.label}</span>
              {value === option.value && (
                <span aria-hidden="true">✓</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}