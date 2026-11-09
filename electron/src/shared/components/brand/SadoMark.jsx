import React from 'react';

/**
 * Sado's compact mark: four waveform bars, the same silhouette the desktop
 * icon, favicon and installer use. App chrome keeps it transparent so it
 * stays crisp at titlebar sizes and in every theme.
 */
export default function SadoMark({ className = '', title, ...props }) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      className={className}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      <g fill="currentColor">
        <rect x="16.81" y="24.81" width="6" height="14.38" rx="1.75" />
        <rect x="24.94" y="17.31" width="6" height="29.38" rx="1.75" />
        <rect x="33.06" y="21.38" width="6" height="21.25" rx="1.75" />
        <rect x="41.19" y="26.84" width="6" height="10.31" rx="1.75" />
      </g>
    </svg>
  );
}
