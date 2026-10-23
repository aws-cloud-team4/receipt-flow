/** A filter-row search field with a clear button. */
export default function SearchBox({ value, onChange, placeholder }: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <span className="search-box">
      <svg viewBox="0 0 24 24" aria-hidden width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        aria-label="검색" />
      {value && <button type="button" onClick={() => onChange("")} aria-label="검색어 지우기">✕</button>}
    </span>
  );
}
