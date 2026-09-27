type LogoPlaceholderProps = {
  className?: string;
  src?: string | null;
  alt?: string;
};

export default function LogoPlaceholder({ className = "", src, alt }: LogoPlaceholderProps) {
  if (src) {
    return (
      <div className={`logo-placeholder logo-placeholder-img ${className}`.trim()}>
        <img src={src} alt={alt ?? "Logo de la cooperativa"} />
      </div>
    );
  }

  return (
    <div className={`logo-placeholder ${className}`.trim()} aria-label={alt ?? "Logo de la cooperativa"}>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2 3 7v3h18V7L12 2Z" fill="currentColor" opacity="0.85" />
        <path d="M5 11h3v9H5v-9Zm5.5 0h3v9h-3v-9ZM16 11h3v9h-3v-9ZM3 21h18v2H3v-2Z" fill="currentColor" />
      </svg>
    </div>
  );
}
