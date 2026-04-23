import React from "react";

export default function Button({ children, disabled, onClick, className = "", type = "button", title }) {
  return (
    <button
      type={type}
      className={`btn-primary ${disabled ? "btn-disabled" : ""} ${className}`.trim()}
      onClick={onClick}
      disabled={disabled}
      title={title}
    >
      {children}
    </button>
  );
}
