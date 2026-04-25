import { useState, type FormEvent } from "react";

interface SearchBarProps {
  onSubmit: (question: string) => void;
  disabled: boolean;
}

export function SearchBar({ onSubmit, disabled }: SearchBarProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-4xl mx-auto flex gap-3 items-stretch"
    >
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        placeholder="Ask anything. Three agents will research, critique, and synthesize."
        className="flex-1 px-5 py-3 rounded-xl bg-slate-800/70 border border-slate-700 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 disabled:opacity-50 transition"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="px-6 py-3 rounded-xl bg-indigo-500 text-white font-medium hover:bg-indigo-400 active:bg-indigo-600 disabled:bg-slate-700 disabled:text-slate-400 disabled:cursor-not-allowed transition"
      >
        {disabled ? "Researching…" : "Research"}
      </button>
    </form>
  );
}
