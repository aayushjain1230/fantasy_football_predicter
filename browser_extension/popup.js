document.getElementById("open").addEventListener("click", () => {
  chrome.tabs.create({url: "https://4thdown.streamlit.app/"});
});
