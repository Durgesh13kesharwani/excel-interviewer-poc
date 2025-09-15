document.addEventListener("DOMContentLoaded", () => {
  const startBtn = document.getElementById("start-btn");
  const startScreen = document.getElementById("start-screen");
  const answerForm = document.getElementById("answer-form");
  const answerInput = document.getElementById("answer-input");
  const chatBox = document.getElementById("chat-box");
  const voiceBtn = document.getElementById("voice-btn");
  const videoFeed = document.getElementById("video-feed");
  const proctorStatus = document.getElementById("proctor-status");
  const micStatus = document.getElementById("mic-status");
  const micText = document.getElementById("mic-text");
  const proctorWarning = document.getElementById("proctor-warning");

  const API_URL = "http://127.0.0.1:8000";
  let sessionId = null;
  let recognition = null;
  let isRecording = false;

  // Initialize proctoring (camera and mic)
  async function initProctoring() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      videoFeed.srcObject = stream;
      proctorStatus.textContent = "Camera: Active";
      proctorStatus.classList.add("text-green-400");
      micStatus.classList.add("bg-green-500");
      micText.textContent = "Active";
    } catch (error) {
      proctorStatus.textContent = "Camera: Inactive";
      proctorStatus.classList.remove("text-green-400");
      proctorStatus.classList.add("text-red-400");
      micStatus.classList.remove("bg-green-500");
      micStatus.classList.add("bg-red-500");
      micText.textContent = "Inactive";
      proctorWarning.classList.remove("hidden");
      proctorWarning.textContent = "Proctoring Issue: Camera/Mic Access Denied";
      console.error("Proctoring setup error:", error);
    }
  }

  // Initialize voice recognition
  function initVoiceRecognition() {
    if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
      recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        answerInput.value = transcript;
        toggleVoiceInput(); // Stop recording after result
        submitAnswer(transcript);
      };

      recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        toggleVoiceInput();
        addMessage("Voice input error. Please try again.", "bot-message");
      };
    } else {
      voiceBtn.disabled = true;
      voiceBtn.classList.add("opacity-50", "cursor-not-allowed");
      addMessage("Voice input not supported in this browser.", "bot-message");
    }
  }

  // Toggle voice input
  function toggleVoiceInput() {
    if (!recognition) return;
    if (isRecording) {
      recognition.stop();
      voiceBtn.classList.remove("mic-active");
      isRecording = false;
    } else {
      recognition.start();
      voiceBtn.classList.add("mic-active");
      isRecording = true;
    }
  }

  // Start interview
  startBtn.addEventListener("click", () => {
    initProctoring();
    initVoiceRecognition();
    startInterview();
  });

  // Voice button toggle
  voiceBtn.addEventListener("click", toggleVoiceInput);

  // Submit answer
  answerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const answer = answerInput.value.trim();
    if (answer) {
      submitAnswer(answer);
      answerInput.value = "";
    }
  });

  // API: start
  async function startInterview() {
    startScreen.classList.add("hidden");
    addMessage("Starting the interview...", "bot-message");
    try {
      const response = await fetch(`${API_URL}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_name: "Candidate",
          resume_text: "Resume: Proficient in Excel, Pivot Tables, XLOOKUP, Power Query, SUMIFS, Charts, VBA macros, Solver; Projects: Built sales dashboard, optimized inventory cleanup; Experience: Finance Analyst (2 years), Operations Reporting (1 year).",
          role: "Analyst",
          level: "Intermediate"
        }),
      });
      if (!response.ok) {
        if (response.status === 422) {
          const errorData = await response.json();
          console.error("Validation error details:", errorData);
          addMessage(`Error: Invalid input - ${JSON.stringify(errorData.detail)}`, "bot-message");
          return;
        }
        throw new Error("Failed to start interview.");
      }
      const data = await response.json();
      sessionId = data.session_id;
      if (data.blocked) {
        addMessage(data.greeting || "Insufficient skill match to proceed.", "bot-message");
        return;
      }
      addMessage(data.greeting, "bot-message");
      displayQuestion(data.question);
      answerForm.classList.remove("hidden");
    } catch (error) {
      console.error("Start interview error:", error);
      addMessage(`Error: ${error.message}`, "bot-message");
    }
  }

  // API: submit
  async function submitAnswer(answer) {
    addMessage(answer, "user-message");
    try {
      const response = await fetch(`${API_URL}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer }),
      });
      if (!response.ok) {
        if (response.status === 422) {
          const errorData = await response.json();
          console.error("Validation error details:", errorData);
          addMessage(`Error: Invalid input - ${JSON.stringify(errorData.detail)}`, "bot-message");
          return;
        }
        throw new Error("Failed to submit answer.");
      }
      const data = await response.json();
      addMessage(data.feedback, "bot-message");
      if (data.next_question) {
        displayQuestion(data.next_question);
      } else if (data.summary) {
        displaySummary(data.summary);
        answerForm.classList.add("hidden");
      }
    } catch (error) {
      console.error("Submit answer error:", error);
      addMessage(`Error: ${error.message}`, "bot-message");
    }
  }

  // UI helper: append message
  function addMessage(text, className) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${className} p-3 rounded-lg max-w-[80%] ${className === "bot-message" ? "bg-gray-700 text-gray-200" : "bg-blue-600 text-white ml-auto"}`;
    messageDiv.innerText = text;
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // Render question text; MCQ options as newline list
  function displayQuestion(question) {
    let questionText = `Question ${question.id}: ${question.text}`;
    if (question.type === "multiple_choice" && question.options) {
      questionText += "\n\n" + question.options.join("\n");
    }
    addMessage(questionText, "bot-message");
  }

  // Show summary
  function displaySummary(summary) {
    addMessage(summary, "bot-message");
  }
});