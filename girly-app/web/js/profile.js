/* Girly 🌸 — profile editor */

let profilePicture = "";

(async function () {
  const me = await Girly.requireAuth();
  if (!me) return;

  Girly.mountChrome({
    active: "profile",
    name: me.user.name,
    profilePicture: me.user.profile_picture,
    showAdmin: Girly.isAuthorizedAdmin(me.user),
  });

  const name = document.getElementById("profile-name");
  const email = document.getElementById("profile-email");
  const dob = document.getElementById("profile-dob");
  const sex = document.getElementById("profile-sex");
  const length = document.getElementById("profile-period-length");
  const lengthValue = document.getElementById("profile-period-value");
  const preview = document.getElementById("profile-preview");
  const pictureInput = document.getElementById("profile-picture-input");
  const error = document.getElementById("profile-error");

  name.value = me.user.name || "";
  email.value = me.user.email || "";
  dob.value = me.user.dob || "";
  sex.value = me.user.bio_sex || "prefer_not_to_say";
  length.value = me.user.period_length || 5;
  profilePicture = me.user.profile_picture || "";
  renderPreview();
  updateLength();

  length.addEventListener("input", updateLength);
  pictureInput.addEventListener("change", () => {
    const file = pictureInput.files?.[0];
    if (!file) return;
    if (file.size > 1500000) {
      error.textContent = "Please choose an image smaller than 1.5 MB.";
      pictureInput.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      profilePicture = String(reader.result || "");
      error.textContent = "";
      renderPreview();
    };
    reader.readAsDataURL(file);
  });

  document.getElementById("remove-picture").addEventListener("click", () => {
    profilePicture = "";
    pictureInput.value = "";
    renderPreview();
  });

  document.getElementById("profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const button = document.getElementById("save-profile");
    button.disabled = true;
    try {
      const updated = await Girly.api("/api/profile", {
        method: "PUT",
        body: JSON.stringify({
          name: name.value.trim(),
          dob: dob.value,
          bio_sex: sex.value,
          period_length: Number(length.value),
          profile_picture: profilePicture,
        }),
      });
      profilePicture = updated.profile_picture || "";
      renderPreview();
      Girly.toast("Profile updated", "check_circle");
      setTimeout(() => { window.location.href = "tracker.html"; }, 500);
    } catch (err) {
      error.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });

  function updateLength() {
    lengthValue.textContent = `${length.value} days`;
    const minDays = Number(length.min);
    const maxDays = Number(length.max);
    const progress = ((Number(length.value) - minDays) / (maxDays - minDays)) * 100;
    length.style.background = `linear-gradient(to right, var(--primary) 0%, var(--primary) ${progress}%, var(--surface-container-high) ${progress}%, var(--surface-container-high) 100%)`;
  }

  function renderPreview() {
    if (profilePicture) {
      preview.innerHTML = `<img src="${Girly.escapeHtml(profilePicture)}" alt="Profile picture" style="width:100%;height:100%;object-fit:cover;border-radius:inherit"/>`;
    } else {
      preview.textContent = Girly.initials(name.value || "G");
    }
  }
})();
