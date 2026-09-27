type FilePickerProps = {
  id: string;
  file: File | null;
  onChange: (file: File | null) => void;
  accept?: string;
  buttonLabel?: string;
  required?: boolean;
};

export default function FilePicker({
  id,
  file,
  onChange,
  accept,
  buttonLabel = "Elegir archivo",
  required,
}: FilePickerProps) {
  return (
    <div className="file-picker">
      <input
        id={id}
        type="file"
        className="file-picker-input"
        accept={accept}
        required={required}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <div className={`file-picker-file${file ? " has-file" : ""}`}>
        <label htmlFor={id} className={`file-picker-button${file ? " has-file" : ""}`}>
          <span className="file-picker-icon" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 4v16m-8-8h16"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              />
            </svg>
          </span>
          <span className="file-picker-label-text">{file ? file.name : buttonLabel}</span>
        </label>
        {file && (
          <button
            type="button"
            className="file-picker-clear"
            aria-label="Quitar archivo"
            onClick={() => onChange(null)}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
              <path
                d="M5 5 19 19M19 5 5 19"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
