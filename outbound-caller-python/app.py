import streamlit as st
import subprocess
import os

st.set_page_config(page_title="LiveKit Outbound Caller", layout="centered")
st.title("📞 LiveKit Outbound Caller")

st.write("Enter the phone number to call below and click 'Dispatch Call' to initiate an outbound call.")

phone_number = st.text_input("Phone Number (e.g., +1234567890)", value="+918980579954")
transfer_to_number = st.text_input("Transfer To Number (e.g., +17345214522)", value="+17345214522")

if st.button("Dispatch Call"):
    if not phone_number.strip():
        st.error("Please enter a phone number to call.")
    else:
        # Construct the metadata string with the input phone numbers
        metadata = f'{{"phone_number": "{phone_number}", "transfer_to": "{transfer_to_number}"}}'

        # The LiveKit CLI will pick up LIVEKIT_API_KEY and LIVEKIT_URL from environment variables
        # Make sure you have set them in your .env file or directly in your environment.
        command = [
            "lk",
            "dispatch",
            "create",
            "--new-room",
            "--agent-name",
            "outbound-caller",
            "--metadata",
            metadata,
        ]

        # Set the PATH for the subprocess to include the local bin directory
        env = os.environ.copy()
        env["PATH"] = os.path.abspath(os.path.join(os.getcwd(), "bin")) + os.pathsep + env["PATH"]

        st.info(f"Dispatching call to {phone_number}...")

        try:
            # Run the command and capture output
            result = subprocess.run(command, capture_output=True, text=True, check=True, env=env)
            st.success(f"Call dispatched successfully! \nOutput:\n{result.stdout}")
            if result.stderr:
                st.warning(f"Warnings/Errors from dispatch command:\n{result.stderr}")
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to dispatch call. Error:\n{e.stderr}\n{e.stdout}")
        except FileNotFoundError:
            st.error("LiveKit CLI (lk) not found. Please ensure it's installed and in your system's PATH.")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}") 