import React from 'react';

export const SignalLogo = ({ className = "h-6 w-6", style = {} }) => {
  return (
    <svg 
      xmlns="http://www.w3.org/2000/svg" 
      viewBox="0 0 24 24" 
      className={className}
      style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
    >
      <defs>
        <linearGradient id="reactSignalGrad" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="50%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <path d="M4.5 10.5C7.5 5.5 12.5 4 16.5 6.5" fill="none" stroke="url(#reactSignalGrad)" strokeWidth="1.75" strokeLinecap="round" opacity="0.3" />
      <path d="M7.5 13.5C9.5 10 13 9 15.5 10.5" fill="none" stroke="url(#reactSignalGrad)" strokeWidth="1.75" strokeLinecap="round" opacity="0.6" />
      <line x1="4" y1="20" x2="14" y2="10" stroke="url(#reactSignalGrad)" strokeWidth="2.25" strokeLinecap="round" />
      <circle cx="14" cy="10" r="4" fill="none" stroke="#10b981" strokeWidth="1" opacity="0.4" />
      <circle cx="14" cy="10" r="2.2" fill="#10b981" />
      <circle cx="18" cy="7" r="1.2" fill="#3b82f6" opacity="0.7" />
      <circle cx="11" cy="6" r="0.9" fill="#2563eb" opacity="0.4" />
      <circle cx="16" cy="14" r="1.2" fill="#10b981" opacity="0.5" />
    </svg>
  );
};

export const SearchIcon = ({ className = "h-4 w-4", style = {} }) => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    viewBox="0 0 24 24" 
    fill="none" 
    stroke="currentColor" 
    strokeWidth="2" 
    strokeLinecap="round" 
    strokeLinejoin="round" 
    className={className}
    style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
  >
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

export const QueueIcon = ({ className = "h-4 w-4", style = {} }) => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    viewBox="0 0 24 24" 
    fill="none" 
    stroke="currentColor" 
    strokeWidth="2" 
    strokeLinecap="round" 
    strokeLinejoin="round" 
    className={className}
    style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
  >
    <line x1="3" y1="6" x2="21" y2="6" />
    <line x1="3" y1="12" x2="16" y2="12" />
    <line x1="3" y1="18" x2="10" y2="18" />
  </svg>
);

export const ThemeIcon = ({ light, className = "h-5 w-5", style = {} }) => {
  if (light) {
    // Sun ray ring
    return (
      <svg 
        xmlns="http://www.w3.org/2000/svg" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        strokeWidth="2" 
        strokeLinecap="round" 
        strokeLinejoin="round" 
        className={className}
        style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
      >
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>
    );
  } else {
    // Moon crescent
    return (
      <svg 
        xmlns="http://www.w3.org/2000/svg" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        strokeWidth="2" 
        strokeLinecap="round" 
        strokeLinejoin="round" 
        className={className}
        style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    );
  }
};
