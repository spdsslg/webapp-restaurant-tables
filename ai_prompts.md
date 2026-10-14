I want to create an for table reservation for one restaurant. it will have three roles: Customer, Staff aka Manager and Admin aka Owner. I am going to use Flask for backend, and Postgres as the primary database. All the frontend will be formed of Jinja2 templated htmls and css. I have created a general plan of what i will use and the specifics of the project, can you check if it is reasonable and give possible refinements.

- Docker Compose will be used from the beginning, with complete features implemented and tested incrementally.
Customer, manager, and administrator roles.
- Managers operate the restaurant. Administrators manage accounts and manager access, and retain manager permissions. Managers cannot assign roles or manage other managers. Prefer deactivation to deleting accounts with reservation history; protect the last active administrator.
- Monday–Friday: 09:00–22:00. Saturday–Sunday: 10:00–21:00.
- Customers select a reservation duration of at most three hours from allowed increments. Start times come from predefined slots.
- Minimum duration is fixed at 30 minutes. Selectable durations are 30/60/90/120/150/180 minutes
- Opening hours and 30-minute start-slot interval are fixed. 
- Managers can create/rename/deactivate tables and browse/filter/cancel customer reservations.

Can you check the current html base that i have and basic css, and change the style to be more appealing to the user.

I want you to create dosctring for the current functions in the backend.   -  was used several times

Create tests for the current code.  -  was used several times

Check out all htmls and css that i have now, and style them properly, as you did with html base.  -  was used several times


Check the current logic of user authentication, and refine it. Give explanations of what you did and why you chose such strategy. For the context of the project, check README.

I want the app to use CSRF to avoid sharing cookies with other websites, chek the current code and set cookie flags and other stuff that is needed to implement it. Give your reasoning and overall changes description. 

How to properly implement first admin setup? I cant create first admin account from the website. Are there some workarounds?

Add administrator-only user/manager management, role assignment and account deactivation.
Preserve accounts referenced by booking history.
Verify managers cannot access actions that are available only for Admins and changed permissions take effect for existing sessions.

I want to implement manahement for staff/managers. This is what is needed to be implemented:
Managers and administrators list, create, rename, and deactivate physical restaurant tables.
Choose a positive capacity when creating a table, keep capacity fixed afterward.
Customers cannot read staff screens or submit these actions.
Preserve table IDs and reservation history. Deactivation prevents new bookings without silently canceling existing reservations

Create a normal readme that describes the project and gives setup instructions.
