function readyMessage() {
  message = document.querySelector("#status_message");
  if (message != null) {
    message.innerHTML = "Complete!";
  }
}

// document.addEventListener("DOMContentLoaded", async () => {
//   const response = await fetch("/allsongs");
//   const songs = await response.json();
//   const tbody = document.querySelector("#song_table tbody");
//   for (const song of songs) {
//     const row = `
//           <tr>
//               <td>${song.title}</td>
//               <td>${song.artist}</td>
//               <td>${
//                 song.video_title
//                   ? `<a href="https://www.youtube.com/watch?v=${song.video_id}" target="_blank">${song.video_title}</a>`
//                   : "Not found"
//               }</td>
//           </tr>
//       `;
//     tbody.insertAdjacentHTML("beforeend", row);
//   }
// });
