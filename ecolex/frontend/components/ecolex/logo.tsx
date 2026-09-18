/** Logo de marca exportado tal cual del design system de Stitch. */
export function EcolexLogo({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" fill="none" className={className}>
      <g transform="translate(10, 8)">
        <rect width="44" height="44" rx="10" fill="#1B4332" />
        <path
          d="M22 10C22 10 32 14 32 24C32 30 27 34 22 34C17 34 12 30 12 24C12 14 22 10 22 10Z"
          fill="#52B788"
        />
        <path d="M22 12V32" stroke="#1B4332" strokeWidth="2" strokeLinecap="round" />
        <path d="M17 20C19 22 22 22 22 22" stroke="#1B4332" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M27 24C25 26 22 26 22 26" stroke="#1B4332" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="34" cy="14" r="3" fill="#D8F3DC" />
      </g>
      <text
        x="66"
        y="37"
        fontFamily="'Plus Jakarta Sans', Inter, sans-serif"
        fontWeight="800"
        fontSize="26"
        fill="#1B4332"
        letterSpacing="-0.5px"
      >
        Ecolex
      </text>
      <text
        x="156"
        y="27"
        fontFamily="'Plus Jakarta Sans', Inter, sans-serif"
        fontWeight="600"
        fontSize="9"
        fill="#52B788"
        letterSpacing="1.2px"
      >
        LEGAL AI
      </text>
      <rect x="156" y="32" width="62" height="12" rx="3" fill="#E8F5EE" />
      <text
        x="160"
        y="41"
        fontFamily="Inter, sans-serif"
        fontWeight="600"
        fontSize="7.5"
        fill="#1B4332"
        letterSpacing="0.4px"
      >
        COLOMBIA
      </text>
    </svg>
  );
}

/** Version compacta (solo el icono cuadrado) usada en el sidebar y header. */
export function EcolexMark({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" fill="none" className={className}>
      <rect width="44" height="44" rx="10" fill="#1B4332" />
      <path
        d="M22 10C22 10 32 14 32 24C32 30 27 34 22 34C17 34 12 30 12 24C12 14 22 10 22 10Z"
        fill="#52B788"
      />
      <path d="M22 12V32" stroke="#1B4332" strokeWidth="2" strokeLinecap="round" />
      <path d="M17 20C19 22 22 22 22 22" stroke="#1B4332" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M27 24C25 26 22 26 22 26" stroke="#1B4332" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="34" cy="14" r="3" fill="#D8F3DC" />
    </svg>
  );
}
