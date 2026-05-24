module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Playfair Display", "Georgia", "serif"],
      },
      colors: {
        brand: {
          50: "#edfff6",
          100: "#d5ffec",
          200: "#aeffda",
          300: "#70ffc0",
          400: "#00e87e",
          500: "#00c062",
          600: "#009650",
          700: "#067542",
          800: "#075f38",
          900: "#013620",
          950: "#011f12",
        },
        dark: {
          50: "#f4f6f4",
          100: "#e3e8e3",
          200: "#c8d2c8",
          300: "#a0b0a0",
          400: "#728872",
          500: "#556855",
          600: "#435343",
          700: "#374437",
          800: "#2d382d",
          900: "#1e261e",
          950: "#111811",
        },
      },
    },
  },
};
