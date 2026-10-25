Family Stories — UI Workflow and Implementation Specification
1. Product Overview
Build a family app that helps relatives preserve stories, share memories, maintain family connections, and celebrate important events.
The home page contains six main features:
Capture an object
Important dates
Family tree
Family memories
Bedtime stories
Timeline
Notifications and the profile menu appear in the header.
A user can both request stories and tell stories. These are actions within the same account, not separate account types.
2. Onboarding and Display Preferences
Account setup
Ask users to provide:
Name
Email
Age
Preferred language
Profile photo or AI avatar
Age selection
Display a horizontal slider with a circular handle. Show the selected age above the slider.
Provide a numeric input or plus/minus buttons as an alternative.
Default interface modes
Age
Default mode
Interface behavior
Below 18
Regular
Full navigation and visual content cards
18–50 inclusive
Simplified
Fewer visible controls and clear labels
Above 50
Extra simple
Large buttons, large text, and one primary action per screen

Users can change their display mode in the profile menu.
Every mode must support all six features.
Extra simple mode requirements
Use large buttons with text labels.
Keep instructions short.
Present one question at a time.
Keep Back and Home controls visible.
Avoid essential actions that require gestures.
Keep recording controls easy to identify.
Use short descriptions with an optional Read more action.
3. Home Page

Header
Display:
App name or logo
Notifications button with an unread indicator
Profile button
Main feature cards
Feature
Supporting text
Destination
Capture an object
Discover the story behind an object
Camera screen
Important dates
Remember birthdays and family events
Calendar
Family tree
Explore and grow your family connections
Family tree
Family memories
Photos with the stories behind them
Memory gallery
Bedtime stories
Create stories in your native language
Parent eligibility check
Timeline
Explore your family’s history
Vertical timeline

Object-story request tracking and story archives belong inside the Capture an object feature. They are not additional main home cards.
4. Capture an Object
Purpose
A listener captures an object to discover its family story.
If the object already has a published story, the listener can play it. Otherwise, the listener requests a story from a family member.
Step 1: Open the camera
When the user selects Capture an object, show:
Live camera preview
Square framing guide
Photo and Video selector
Capture button
Switch camera button
Upload existing media option
Back button
Instruction: Place the object inside the frame.
Photo is the default mode.
Video must record audio. Show a recording indicator, elapsed time, and a Stop button.
Request camera and microphone permissions when needed. If access is unavailable, offer an upload alternative.
Step 2: Review the capture
Show the captured photo or a playable video preview with sound.
Heading: Can you see the object clearly?
Actions:
Retake: Return to the camera.
Use photo / Use video: Approve the capture and continue.
Do not upload or submit a story request until the user approves the capture.
Step 3: Search the family archive
After approval:
Upload the media.
Save the capture record.
Search the authorized family archive for matching objects.
Check for published stories and pending requests.
Loading message: Looking for this object’s story…
Search result
Behavior
Possible object match
Ask the listener to confirm the object
Several possible matches
Show a short selection list with None of these
Confirmed object with a published story
Open story playback
Confirmed object with a pending request
Show the existing request status
Object without a story
Continue to storyteller selection
No matching object
Create an object record and continue
Search failure
Offer Try again or Request a story anyway

A visually similar object must not automatically be treated as the same object.
Step 4: Select a storyteller
Heading: Who might know its story?
Display family members as selectable cards with names and profile images.
After selection, show:
Object preview
Selected family member
Optional short question
Send request button
Example question: Grandpa, who gave you this watch?
Save the request before displaying success. Notify the selected storyteller.
Step 5: Show request confirmation
Heading: Story requested
Message: We’ve asked Grandpa about this object. We’ll let you know when the story is ready.
Actions:
Back to home
View request
The request remains pending after the listener leaves the screen.
Step 6: Storyteller opens the request
Display:
Requester’s name
Object photo or video
Requester’s question
Tell the story
Later
I don’t know this story
Step 7: Record the story
Offer audio or video recording.
Display:
Object preview
Start recording
Pause and resume
Finish recording
Recording timer
Initial prompt: Tell us about this object.
Optional follow-up questions:
Who gave it to you?
When did you get it?
Why is it important to you?
Ask one question at a time in the storyteller’s selected language. Allow skipping questions.
Avoid asking for details already provided.
Step 8: Review and publish
Display:
Recording playback
Editable title
Short editable description
Record again
Save draft
Share story
If AI generates text, the storyteller must be able to edit it before publishing. Do not invent missing family information.
On publication:
Save the story.
Link it to the object.
Complete the associated request.
Notify the listener.
Step 9: Play the completed story
Display:
Object title and image
Storyteller’s name
Video or object imagery with recorded narration
Playback controls
Transcript when available
Use the relative’s actual recording as the primary narration.
5. Important Dates

Purpose
Show birthdays, anniversaries, family functions, and cultural functions in a calendar limited to the current year.
Initial view
Open the current month and highlight today.
Use gold to mark dates containing important events. Distinguish today’s indicator from event markers.
Month view
Display:
Month and current year
Calendar grid
Gold event markers
Previous and next month controls
Year overview control
Add event button
Month navigation must remain within the current year.
Year overview
Zooming out opens a panel containing 12 mini month calendars.
Each mini calendar displays its days and gold event markers.
Selecting a month opens that month.
Provide visible Month and Year controls so the feature does not depend on pinch gestures.
Do not allow navigation to previous or future years.
Selecting a date
Situation
Result
No events
Show No important events on this date
One event
Open event details
Multiple events
Show a list of events for that date

Event details
Display:
Event title
Event category
Date
Time, if provided
Short description
Related family members
Creating an event
Fields:
Title
Category
Date
Optional time
Short description
Related family members
Optional annual recurrence
Suggested MVP permission: members can create events and edit or delete events they created.
Annual birthdays and anniversaries appear in the current year. Cultural events must support explicit occurrence dates because their Gregorian dates may change.
6. Family Tree
Purpose
Allow members to build an extended family tree through accepted account invitations.
Initial state
Show only the current user until family connections are accepted.
Each person appears as a node containing:
Name
Profile photo or AI avatar
Relationship label
Profile image choice
Allow each member to:
Upload a photo
Create an AI avatar using Muse
Show a placeholder until an image is available.
Muse avatar generation requires an available integration. Members control their own profile images.
Add-member controls
When a person is selected, show square plus buttons:
Position
Suggested action
Above the person
Add parent
Below the person
Add child
Beside the person
Choose sibling or partner

Confirm the relationship in the invitation dialog. The relationship must be anchored to the selected person.
Invitation workflow
Select a person in the tree.
Tap a plus button.
Open an invitation dialog.
Show whose relative is being added.
Select or confirm the relationship.
Enter the relative’s account email.
Verify that the account exists.
Validate the proposed relationship.
Save a pending invitation.
Notify the invited account.
The invited person does not appear as an accepted family member before accepting.
Invitation dialog
Display:
Selected person’s name
Proposed relationship
Email field
Send invitation
Cancel
If no account exists, explain that the relative must create an account first.
Recipient response
Display:
Inviter’s name
Family context
Proposed relationship
Accept
Decline
If accepted:
Create the relationship.
Add family membership when needed.
Update the tree.
Notify the inviter.
If declined:
Mark the invitation declined.
Notify the inviter.
Do not create the relationship or grant family access.
Extending the family tree
Every accepted member can add relatives using the same process.
Examples:
Select your father and add his sister as his sibling.
Select your grandfather and add his parent.
Select an aunt and add her child.
Reuse existing account nodes instead of duplicating them.
Prevent invalid relationships, including a person becoming their own ancestor.
An invitation must not silently merge separate private family archives.
Tree navigation
Support:
Pan
Zoom
Select person
Center on me
Expand family branches
Current scope limitation
Every added person must already have an account. Adding deceased or non-account ancestors requires a separate ancestor-profile feature.
7. Family Memories
Purpose
Allow family members to share photographs with recorded audio explaining the memories behind them.
Examples:
Family trips
Family functions
Childhood photographs
Old photographs of parents or grandparents
Gallery screen
Display memory cards containing:
Cover photo
Title
Contributor’s name
Play story button
Provide an Add memory action.
Create a memory
Select one or more photos.
Preview and reorder them.
Record the story behind the photos.
Answer optional follow-up questions.
Add a title.
Optionally add the event date.
Review photos and audio.
Publish or save a draft.
Use the contributor’s selected language for questions.
Publishing requirements
At least one photo is required.
Recorded story audio is required.
Drafts may contain photos before audio is completed.
This feature does not generate a video.
Memory detail screen
Display:
Photo or photo gallery
Title
Contributor’s name
Event date, when known
Short description, if provided
Play and pause controls
Audio progress
Authorized members of the same family can view the photos and listen to the story.
8.Schedule 
## 8. Family Availability

### Purpose

Let family members add their schedules and check whether relatives are free right now.

Only members connected through the accepted family tree can see each other’s availability. Personal schedules and event details remain private.

### Main UI Change

Replace the **Bedtime stories** home card with:

**Family availability**  
Supporting text: **See who is free right now.**

### Access

- Users must belong to the same accepted family tree.
- Pending or declined invitations do not grant access.
- Users can view and edit only their own schedules.

### Availability Screen

When the user opens Family availability, display family members as cards containing:

- Name
- Profile photo or avatar
- Current availability
- View status button

Supported statuses:

| Status | Meaning |
|---|---|
| Free now | The member has shared availability and has no active busy period |
| Busy now | The member has an active busy period or manual Busy status |
| Not shared | The member has disabled availability sharing or has not configured it |

Do not assume a member is free simply because they have not added a schedule.

### Selecting a Family Member

Show:

- Name and profile image
- **Free right now**, **Busy right now**, or **Availability not shared**
- Last updated time

Do not show:

- Their calendar
- Event titles or descriptions
- Locations
- Reasons for being busy
- Upcoming commitments
- When their current activity ends

### Add My Schedule

Provide a **My schedule** button on the availability screen.

Users can:

1. Add a busy period.
2. Choose its date.
3. Enter its start and end times.
4. Optionally repeat it on selected weekdays.
5. Save, edit, or delete it.

A private label, such as **Class** or **Work**, may help the owner organize entries. It must never appear to other family members.

### Availability Calculation

- Mark a member Busy when the current time falls within a saved busy period.
- Mark them Free outside busy periods only after they enable sharing and confirm that their schedule is ready.
- Recalculate status when a busy period starts or ends.
- Support overlapping entries and periods that cross midnight.
- Store the schedule’s time zone and calculate status correctly across family members’ locations.

### Manual Status Override

Allow users to temporarily select:

- **Set myself as free**
- **Set myself as busy**

Require an expiry time for the override. After expiry, return to schedule-based availability.

Manual status takes priority over the saved schedule.

### Privacy Controls

Provide an **Availability sharing** toggle.

- Sharing is off until the user enables it.
- Turning it off immediately changes the public status to Not shared.
- Schedule entries remain private even when sharing is enabled.
- The backend must return only the current availability to other family members, not the underlying schedule entries.

### Empty and Error States

- No connected relatives: **Add family members to see their availability.**
- Sharing disabled: **Your availability is not shared.**
- Status cannot be refreshed: **Availability is temporarily unavailable.**

Do not display an outdated status as current.

### Minimum Data Model

| Record | Main fields |
|---|---|
| Availability settings | User ID, sharing enabled, schedule configured, time zone |
| Private schedule entry | User ID, optional private label, start, end, recurrence, time zone |
| Manual override | User ID, Free or Busy status, expiry time |
| Availability response | Member ID, current status, last updated time |

### Acceptance Checklist

- [ ] Family availability replaces Bedtime stories on the home page.
- [ ] Only accepted family members appear.
- [ ] Users can add, edit, and delete their own busy periods.
- [ ] Repeating schedules and time zones are supported.
- [ ] Relatives see only current Free, Busy, or Not shared status.
- [ ] Schedule details remain private.
- [ ] Manual overrides expire automatically.
- [ ] Disabling sharing immediately hides availability.
- [ ] Missing schedules and refresh failures never incorrectly show Free.

9. Timeline
Purpose
Present family history along one straight vertical line.
Layout
Display short event cards branching from the line.
Each card contains:
Event title
Date
Time, when known
Short description
Do not include audio or video.
Content sources
Include:
Family milestones
Family functions
Cultural events
Dated family memories
Reuse existing family event records rather than creating duplicate timeline entries.
Date rules
Arrange entries chronologically.
Do not invent missing dates or times.
Label approximate dates clearly.
Include memories only when an event date or approximate date is available.
The timeline can show historical family events. The calendar remains limited to the current year.
10. Notifications
Notification center
The header notification button opens a list of notifications.
Each item displays:
Short message
Relevant person or object image
Timestamp
Read or unread state
Opening an item navigates to the related screen.
Notification types
Trigger
Recipient
Destination
Object story requested
Selected storyteller
Story request
Object story published
Original requester
Story playback
Family invitation received
Invited member
Invitation details
Family invitation accepted
Inviter
Family tree
Family invitation declined
Inviter
Invitation status

Behavior
Maintain in-app notifications even when push notifications are disabled.
Show an unread indicator.
Mark notifications read when opened.
Retry failed notification delivery separately.
Do not undo saved requests or invitations because notification delivery fails.
11. Profile Menu and Language
Profile information
Display:
Name
Profile photo or avatar
Family relationship context
Selected language
A person can have several relationships. Use labels such as Parent of Maya or Child of Ram rather than storing one fixed family position.
Menu actions
Edit profile
Choose language
Choose display mode
Sign out
Language behavior
The selected language controls:
Navigation labels
Buttons
Instructions
Error messages
Notifications
Story-recording questions
Follow-up questions
Changing the app language must not modify original recordings.
Translated transcripts or subtitles, if implemented, should remain separate from the original content.
Use English as a fallback when interface translations are unavailable.
12. Minimum Data Model
Record
Main fields
User
ID, email, name, age, preferred language, display mode, photo, avatar
Family
ID, name, creator
Family membership
Family ID, user ID, membership status
Family relationship
Family ID, person A, person B, relationship type, acceptance date
Family invitation
Inviter, recipient, family, selected person, proposed relationship, status
Object
Family ID, title, cover image, creator
Media
Uploader, media type, storage reference, duration, upload status
Object story request
Object, capture, requester, storyteller, question, status
Object story
Object, optional request, storyteller, recording, title, description, language, status
Family event
Family, creator, title, category, date, optional time, date precision, description, related people, recurrence
Family memory
Family, contributor, photos, audio, title, optional date, date precision, language, status
Bedtime story
Parent, child, language, theme, title, story text, creation date
Notification
Recipient, type, related record, read timestamp, creation date

Store media files in file storage and their references in the database.
13. Status Definitions
Item
Supported statuses
Family invitation
Pending, accepted, declined, cancelled
Object story request
Pending, in progress, completed, declined, cancelled
Object story
Draft, published
Family memory
Draft, published
Media upload
Uploading, ready, failed

Accepting an invitation creates the family connection.
Publishing an object story completes its associated request.
Saving a draft must not mark a request completed.
14. Implementation Requirements
Use real persistence for accounts, relationships, requests, stories, and memories.
Restrict family content to authorized members.
Preserve drafts and approved captures.
Provide upload progress and retry controls.
Prevent duplicate submissions.
Show success only after saving completes.
Validate family relationships before accepting them.
Keep all six features available in every display mode.
Use short, clear interface text.
Keep AI-generated content editable.
Do not invent family facts, relationships, dates, or recordings.
Clearly identify demo placeholders during development.
15. MVP Acceptance Checklist
Home displays the six specified feature cards.
Notifications and profile controls appear in the header.
Photo and video capture support review and retake.
Video capture includes audio.
Known objects open confirmed existing stories.
Unknown objects can trigger story requests.
Storytellers can record, review, save drafts, and publish.
The calendar supports month and current-year views.
Important dates appear in gold.
Calendar navigation cannot leave the current year.
Family members are added only after invitation acceptance.
Rejected invitations notify the inviter.
Accepted members can extend family branches.
Family memories require photos and recorded audio before publishing.
Family memories do not generate video.
Bedtime story creation checks accepted parent relationships.
Bedtime stories support the selected native language.
The timeline displays chronological text events without audio or video.
App text and recording prompts follow the selected language.
All display modes support the complete workflow.

