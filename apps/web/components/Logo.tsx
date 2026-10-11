export default function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden="true">
      <circle cx="15" cy="15" r="13.5" fill="none" stroke="#E0A245" strokeWidth="1.8" />
      <path d="M6 18c4-6 9-6 18-3" stroke="#F2F2F2" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <circle cx="11" cy="11" r="2" fill="#E0A245" />
      <circle cx="17" cy="9" r="1.5" fill="#E0A245" />
      <circle cx="21" cy="12" r="1.2" fill="#E0A245" />
    </svg>
  );
}
