// The page reads all score data from the API. Using the page's own host name
// lets a phone on the same Wi-Fi reach the API on the laptop.
window.MICOMETEO_CONFIG = {
  apiBase: `${location.protocol}//${location.hostname}:8080/api/v1`,
};
