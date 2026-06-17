from locust import HttpUser, task, between

class ParticipantUser(HttpUser):
    # Simulate a realistic wait time of 1 to 3 seconds between clicks
    wait_time = between(1, 3)

    @task
    def complete_experiment_flow(self):
        # 1. Load the landing/consent page
        response = self.client.get("/consent")
        if response.status_code != 200:
            return

        # 2. Submit the consent form to generate a MongoDB participant and session
        consent_data = {
            "program": "btech_cs",
            "year_of_study": "3",
            "sc_exposure": "1_2_courses",
            "ai_familiarity": "regularly",
            "gender": "male",
            "consent_read": "on",
            "consent_voluntary": "on",
            "consent_data": "on"
        }
        
        with self.client.post("/consent", data=consent_data, catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Consent failed with {response.status_code}")
                return
            
        # 3. Load the tutorial
        self.client.get("/tutorial")
        
        # 4. Load the first scenario in Stage 1
        self.client.get("/task")
