import { useRef, useState } from "react";
import type { DragEvent } from "react";

type DropZoneProps = {
  id: string;
  files: File[];
  onChange: (files: File[]) => void;
  accept: string;
  multiple?: boolean;
  hint: string;
};

export default function DropZone({ id, files, onChange, accept, multiple = false, hint }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files);
    if (dropped.length === 0) return;
    onChange(multiple ? dropped : dropped.slice(0, 1));
  }

  const hasFiles = files.length > 0;

  return (
    <div
      className={`dropzone${dragging ? " is-dragging" : ""}${hasFiles ? " has-files" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        className="dropzone-input"
        accept={accept}
        multiple={multiple}
        onChange={(e) => onChange(Array.from(e.target.files ?? []))}
      />
      {hasFiles ? (
        <>
          <p className="dropzone-title">
            {files.length === 1 ? files[0].name : `${files.length} archivos seleccionados`}
          </p>
          <p className="dropzone-hint">
            <button type="button" className="dropzone-link" onClick={() => inputRef.current?.click()}>
              Cambiar
            </button>
            {" · "}
            <button type="button" className="dropzone-link" onClick={() => onChange([])}>
              Quitar
            </button>
          </p>
        </>
      ) : (
        <>
          <p className="dropzone-title">
            Arrastrá {multiple ? "los archivos" : "el archivo"} acá o{" "}
            <button type="button" className="dropzone-link" onClick={() => inputRef.current?.click()}>
              elegilo
            </button>
          </p>
          <p className="dropzone-hint">{hint}</p>
        </>
      )}
    </div>
  );
}
