import React from 'react';

interface ProjectEntryComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
}

export const ProjectEntryComposer: React.FC<ProjectEntryComposerProps> = ({
  value,
  onChange,
  onSubmit,
  disabled = false,
  placeholder = '\u5728\u8fd9\u4e2a\u9879\u76ee\u4e2d\u53d1\u8d77\u65b0\u804a\u5929',
}) => {
  const submitDisabled = disabled || !value.trim();

  return (
    <form
      className="project-entry-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (!submitDisabled) {
          onSubmit();
        }
      }}
    >
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            if (!submitDisabled) {
              onSubmit();
            }
          }
        }}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className="project-entry-composer__input"
      />
      <button type="submit" className="project-entry-composer__submit" disabled={submitDisabled}>
        {'\u53d1\u9001'}
      </button>
    </form>
  );
};
